import uuid as uuid_lib
from urllib.parse import urlencode

import jwt
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from .models import AuthEvent, Product, UserProductAccess, Organization, ProductRole, AccessClass
from .forms import FirstPasswordChangeForm, SSODAccessKeyCreateForm
from accounts.services.dominex_client import fetch_oracle_status

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import get_user_model
from django.utils import timezone


import hashlib
import secrets

from django.utils import timezone

from accounts.models import SSODAccessKey

from django_otp_webauthn.models import WebAuthnCredential

SSO_TICKET_LIFETIME_SECONDS = 60

@login_required
def account_home(request):
    """
    Личный кабинет пользователя.

    Если пользователь вошел с временным паролем,
    сразу отправляем его на обязательную смену пароля.
    """

    if request.user.must_change_password:
        return redirect("accounts:change_password")

    return render(request, "accounts/account_home.html")


@login_required
def change_password(request):
    """
    Обязательная смена временного пароля.

    Старый пароль не запрашиваем, потому что пользователь уже вошел.
    """

    if settings.DOMINEX_CONNECTED_MODE:
        # This form writes to CustomUser's local password field, which
        # DominexCredentialBackend never checks - Dominex owns the real
        # credential. Defense in depth: auth_backends.py already forces
        # must_change_password off on every Dominex-verified login, so
        # this view shouldn't normally be reached at all, but block it
        # outright rather than let it silently do nothing useful.
        messages.info(request, "Смена пароля выполняется в Dominex Core.")
        return redirect("accounts:account_home")

    if request.method == "POST":
        form = FirstPasswordChangeForm(request.POST)

        if form.is_valid():
            request.user.set_password(form.cleaned_data["new_password1"])
            request.user.must_change_password = False
            request.user.save(update_fields=["password", "must_change_password"])

            update_session_auth_hash(request, request.user)

            messages.success(request, "Пароль успешно изменен.")

            return redirect("accounts:account_home")

    else:
        form = FirstPasswordChangeForm()


    return render(
        request,
        "accounts/change_password.html",
        {
            "form": form,
        },
    )



@login_required
def access_key_list(request):
    """
    Список ключей доступа текущего пользователя.
    """

    keys = request.user.ssod_keys.order_by("-issued_at")

    return render(
        request,
        "accounts/access_key_list.html",
        {
            "keys": keys,
        },
    )


@login_required
def access_key_create(request):
    """
    Выпуск нового ключа доступа ССОД.

    Секрет показываем пользователю только один раз.
    В базе сохраняем только SHA256 fingerprint.
    """

    generated_secret = None

    if request.method == "POST":
        form = SSODAccessKeyCreateForm(request.POST)

        if form.is_valid():
            generated_secret = f"ssod_{secrets.token_urlsafe(48)}"
            fingerprint = hashlib.sha256(
                generated_secret.encode("utf-8")
            ).hexdigest()

            SSODAccessKey.objects.create(
                user=request.user,
                name=form.cleaned_data["name"],
                fingerprint_sha256=fingerprint,
                status=SSODAccessKey.Status.ACTIVE,
            )

            return render(
                request,
                "accounts/access_key_created.html",
                {
                    "generated_secret": generated_secret,
                    "fingerprint": fingerprint,
                },
            )

    else:
        form = SSODAccessKeyCreateForm()

    return render(
        request,
        "accounts/access_key_form.html",
        {
            "form": form,
        },
    )


@login_required
def access_key_revoke(request, key_uuid):
    """
    Отзыв ключа доступа.

    Отзывать можно только свой ключ.
    """

    if request.method == "POST":
        key = request.user.ssod_keys.get(uuid=key_uuid)

        key.status = SSODAccessKey.Status.REVOKED
        key.revoked_at = timezone.now()
        key.save(update_fields=["status", "revoked_at", "updated_at"])

        messages.success(request, "Ключ доступа отозван.")

    return redirect("accounts:access_key_list")




@login_required
def security(request):
    """
    Страница безопасности пользователя.

    Здесь показываем passkey/WebAuthn-устройства.
    На первом этапе:
    - список зарегистрированных passkey;
    - кнопка добавления нового passkey.
    """

    credentials = WebAuthnCredential.objects.filter(
        user=request.user
    ).order_by("-created_at")

    oracle_status = fetch_oracle_status(request.user.username)

    return render(
        request,
        "accounts/security.html",
        {
            "credentials": credentials,
            "oracle_status": oracle_status,
        },
    )

@login_required
def account_products(request):
    """
    Страница "Мои продукты".

    Пользователь видит активные продукты экосистемы ССОД.

    Доступ считается разрешенным, если для текущего пользователя
    есть запись UserProductAccess со статусом ACTIVE.

    Важно:
    в нашей модели нет поля is_allowed.
    Доступ управляется через status:
    - active
    - suspended
    - revoked
    """

    products = Product.objects.filter(is_active=True)

    active_access_product_ids = set(
        UserProductAccess.objects.filter(
            user=request.user,
            status=UserProductAccess.Status.ACTIVE,
        ).values_list("product_id", flat=True)
    )

    product_cards = []

    for product in products:
        product_cards.append(
            {
                "product": product,
                "is_allowed": product.id in active_access_product_ids,
            }
        )

    return render(
        request,
        "accounts/account_products.html",
        {
            "product_cards": product_cards,
        },
    )


@login_required
def sso_authorize(request, product_code):
    """
    Выдаёт короткоживущий подписанный SSO-тикет для перехода в продукт
    экосистемы (см. dominex/docs/module-interactions.md, "What Is Issued
    On Login" - module access token / ticket layer).

    Требует активный UserProductAccess (та же проверка, что в
    account_products) и product.sso_enabled - иначе продукт просто не
    участвует в тикет-флоу и должен использовать обычный product_url.
    """
    product = Product.objects.filter(code=product_code, is_active=True, sso_enabled=True).first()
    if product is None:
        raise Http404("Продукт не найден или не поддерживает SSO-тикет.")

    is_allowed = UserProductAccess.objects.filter(
        user=request.user,
        product=product,
        status=UserProductAccess.Status.ACTIVE,
    ).exists()
    if not is_allowed:
        messages.error(request, "Нет доступа к этому продукту.")
        return redirect("accounts:account_products")

    next_path = request.GET.get("next", "")
    if not next_path.startswith("/"):
        next_path = ""

    now = timezone.now()
    jti = str(uuid_lib.uuid4())
    payload = {
        "sub": request.user.username,
        "aud": product.code,
        "iat": int(now.timestamp()),
        "exp": int(now.timestamp()) + SSO_TICKET_LIFETIME_SECONDS,
        "jti": jti,
    }
    ticket = jwt.encode(payload, settings.SSO_TICKET_SECRET, algorithm="HS256")

    AuthEvent.objects.create(
        user=request.user,
        event_type=AuthEvent.EventType.ACCESS_GRANTED,
        ip_address=request.META.get("REMOTE_ADDR"),
        user_agent=request.META.get("HTTP_USER_AGENT", ""),
        details={"sso_ticket_issued": True, "product": product.code, "jti": jti, "exp": payload["exp"]},
    )

    query = {"ticket": ticket}
    if next_path:
        query["next"] = next_path
    callback_url = f"{product.product_url.rstrip('/')}/auth/sso/callback?{urlencode(query)}"
    return redirect(callback_url)


@staff_member_required
def roles_rights(request):
    """
    Админская страница "Роли и права".

    Назначение:
    - показать пользователей;
    - показать продукты;
    - дать администратору возможность галочками разрешать/отзывать доступ.

    Важно:
    мы НЕ используем поле is_allowed, потому что его нет.
    Доступ определяется через UserProductAccess.status:

    ACTIVE    — доступ есть;
    REVOKED   — доступ отозван;
    SUSPENDED — доступ временно приостановлен.

    Пока используем базовую роль продукта с code="user".
    Если роли нет — создаем ее автоматически.
    """

    User = get_user_model()

    products = Product.objects.filter(is_active=True).order_by("sort_order", "code")
    users = User.objects.filter(is_active=True).order_by("username")

    # Берем первую организацию как организацию по умолчанию.
    # В дальнейшем лучше привязать организацию прямо к пользователю,
    # если это уже не сделано в модели пользователя.
    default_organization = Organization.objects.first()

    if not default_organization:
        messages.error(
            request,
            "Не создана ни одна организация. Сначала добавьте организацию.",
        )

        return render(
            request,
            "accounts/roles_rights.html",
            {
                "products": products,
                "users": users,
                "active_access_keys": set(),
                "active_access_map": {},
            },
        )





    # Для каждого продукта должна быть базовая роль.
    # Она нужна, потому что UserProductAccess.role обязательное поле.
    default_roles_by_product_id = {}

    for product in products:
        role, created = ProductRole.objects.get_or_create(
            product=product,
            code="user",
            defaults={
                "name": "Пользователь",
                "is_active": True,
            },
        )
        default_roles_by_product_id[product.id] = role

    if request.method == "POST":
        """
        При сохранении формы мы проходим по всем пользователям и продуктам.

        Если checkbox есть в POST:
            ставим status=ACTIVE

        Если checkbox отсутствует:
            если запись доступа уже есть — ставим status=REVOKED
            запись не удаляем, чтобы в будущем сохранять историю.
        """

        for user in users:
            for product in products:
                checkbox_name = f"access_{user.id}_{product.id}"
                checked = checkbox_name in request.POST

                role = default_roles_by_product_id[product.id]

                access, created = UserProductAccess.objects.get_or_create(
                    user=user,
                    product=product,
                    organization=default_organization,
                    role=role,
                    defaults={
                        "access_class": getattr(user, "access_class", AccessClass.G),
                        "status": UserProductAccess.Status.ACTIVE
                        if checked
                        else UserProductAccess.Status.REVOKED,
                        "valid_from": timezone.now(),
                        "comment": "Создано через страницу Роли и права",
                    },
                )

                if not created:
                    access.status = (
                        UserProductAccess.Status.ACTIVE
                        if checked
                        else UserProductAccess.Status.REVOKED
                    )
                    access.save(update_fields=["status", "updated_at"])

        messages.success(request, "Права доступа обновлены.")
        return redirect("accounts:roles_rights")

    # Карта активных доступов для быстрого отображения галочек.
    active_access_keys = {
        f"{user_id}_{product_id}"
        for user_id, product_id in UserProductAccess.objects.filter(
            status=UserProductAccess.Status.ACTIVE,
            product__in=products,
            user__in=users,
        ).values_list("user_id", "product_id")
    }
    active_access_map = {}

    for access_key in active_access_keys:
        active_access_map[access_key] = True

    return render(
        request,
        "accounts/roles_rights.html",
        {
            "products": products,
            "users": users,
            "active_access_keys": active_access_keys,
            "active_access_map": active_access_map,
        },
    )
