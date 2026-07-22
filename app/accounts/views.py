import uuid as uuid_lib
import json
import os
import subprocess
import sys
import tempfile
from urllib.parse import urlencode

import jwt
import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from .models import (
    AuthEvent,
    DeployJob,
    Product,
    ServiceClient,
    ServiceClientGrant,
    UserProductAccess,
    Organization,
    ProductRole,
    AccessClass,
)
from .forms import (
    FirstPasswordChangeForm,
    PortalDeployForm,
    ServiceClientCreateForm,
    ServiceClientGrantCreateForm,
    SSODAccessKeyCreateForm,
)
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


@staff_member_required
def account_integrations(request):
    """
    Админская страница "Интеграции" - управление ServiceClient/
    ServiceClientGrant (межсервисная авторизация, см. accounts.api.
    issue_service_token) и журнал их использования, вместо Django admin.
    Задел под будущие элементы, касающиеся внешних интеграций с другими
    модулями экосистемы - см. dominex/docs/module-interactions.md,
    "Service-to-service auth for new modules".
    """

    clients = ServiceClient.objects.prefetch_related("grants").order_by("code")
    grant_form = ServiceClientGrantCreateForm()
    recent_events = AuthEvent.objects.filter(
        event_type__in=[AuthEvent.EventType.SERVICE_TOKEN_ISSUED, AuthEvent.EventType.SERVICE_TOKEN_DENIED]
    ).order_by("-created_at")[:30]
    deploy_jobs = DeployJob.objects.order_by("-created_at")[:10]

    return render(
        request,
        "accounts/account_integrations.html",
        {
            "clients": clients,
            "grant_form": grant_form,
            "recent_events": recent_events,
            "deploy_jobs": deploy_jobs,
        },
    )


@staff_member_required
def service_client_create(request):
    """Регистрация нового ServiceClient - секрет генерируется здесь и
    показывается один раз (тот же принцип, что и access_key_create для
    SSODAccessKey), в базе остаётся только SHA256-фингерпринт."""

    generated_secret = None

    if request.method == "POST":
        form = ServiceClientCreateForm(request.POST)

        if form.is_valid():
            code = form.cleaned_data["code"]
            if ServiceClient.objects.filter(code=code).exists():
                form.add_error("code", "Клиент с таким кодом уже существует.")
            else:
                generated_secret = secrets.token_urlsafe(32)
                fingerprint = hashlib.sha256(generated_secret.encode("utf-8")).hexdigest()

                ServiceClient.objects.create(
                    code=code,
                    name=form.cleaned_data["name"],
                    client_secret_hash=fingerprint,
                    is_active=True,
                )

                return render(
                    request,
                    "accounts/service_client_created.html",
                    {
                        "code": code,
                        "generated_secret": generated_secret,
                    },
                )
    else:
        form = ServiceClientCreateForm()

    return render(
        request,
        "accounts/service_client_form.html",
        {
            "form": form,
        },
    )


@staff_member_required
def service_client_toggle(request, client_id):
    """Включает/отключает ServiceClient целиком - отключённый клиент не
    сможет получить новый токен ни на один audience (уже выданные
    короткоживущие токены продолжат действовать до истечения exp)."""

    if request.method == "POST":
        client = ServiceClient.objects.get(id=client_id)
        client.is_active = not client.is_active
        client.save(update_fields=["is_active", "updated_at"])
        messages.success(
            request,
            f"Клиент «{client.code}» {'включён' if client.is_active else 'отключён'}.",
        )

    return redirect("accounts:account_integrations")


@staff_member_required
def service_client_grant_create(request, client_id):
    """Добавляет ServiceClientGrant (разрешение на audience) существующему
    клиенту - форма встроена прямо в строку клиента на account_integrations."""

    client = ServiceClient.objects.get(id=client_id)

    if request.method == "POST":
        form = ServiceClientGrantCreateForm(request.POST)

        if form.is_valid():
            audience = form.cleaned_data["audience"]
            grant, created = ServiceClientGrant.objects.get_or_create(
                service_client=client,
                audience=audience,
                defaults={"is_active": True},
            )
            if not created and not grant.is_active:
                grant.is_active = True
                grant.save(update_fields=["is_active", "updated_at"])
            messages.success(request, f"Grant «{audience}» добавлен клиенту «{client.code}».")
        else:
            messages.error(request, "Некорректный audience.")

    return redirect("accounts:account_integrations")


@staff_member_required
def service_client_grant_toggle(request, grant_id):
    """Включает/отключает конкретный grant, не трогая остальные у того
    же клиента."""

    if request.method == "POST":
        grant = ServiceClientGrant.objects.get(id=grant_id)
        grant.is_active = not grant.is_active
        grant.save(update_fields=["is_active", "updated_at"])
        messages.success(
            request,
            f"Grant «{grant.audience}» клиента «{grant.service_client.code}» "
            f"{'включён' if grant.is_active else 'отключён'}.",
        )

    return redirect("accounts:account_integrations")


def _ensure_service_client(org_code):
    """Создаёт (или переиспользует) ServiceClient <org>_portal + grant на
    dominex, возвращает (client, plaintext_secret). Секрет генерируется
    заново при каждом деплое (в БД только хэш)."""
    code = f"{org_code}_portal"
    secret = secrets.token_urlsafe(32)
    fingerprint = hashlib.sha256(secret.encode("utf-8")).hexdigest()
    client, _ = ServiceClient.objects.get_or_create(
        code=code, defaults={"name": f"{org_code} portal", "client_secret_hash": fingerprint, "is_active": True}
    )
    client.client_secret_hash = fingerprint
    client.is_active = True
    client.save(update_fields=["client_secret_hash", "is_active", "updated_at"])
    ServiceClientGrant.objects.get_or_create(
        service_client=client, audience="dominex", defaults={"is_active": True}
    )
    return client, secret


def _ensure_dominex_source(org_code):
    """Создаёт ExternalSource <org>_ad в Dominex через API (идемпотентно).
    Использует X-Dominex-Api-Key (IdentityApiConsumer ssod_auth). Поднимает
    исключение при недоступности - деплой не начнётся с битой интеграцией."""
    code = f"{org_code}_ad"
    resp = requests.post(
        f"{settings.DOMINEX_API_BASE_URL.rstrip('/')}/api/v1/import/sources",
        headers={"X-Dominex-Api-Key": settings.DOMINEX_API_KEY},
        json={"code": code, "name": f"{org_code} (AD)"},
        timeout=15,
    )
    resp.raise_for_status()
    return code


def _build_portal_env(cd, org_code, service_secret, source_code):
    """Собирает словарь .env развёртываемого портала из данных формы (cd),
    автогенерируемых секретов и публичных адресов экосистемы."""
    from cryptography.fernet import Fernet

    db_pass = secrets.token_urlsafe(24)
    return {
        "POSTGRES_DB": f"{org_code}_portal",
        "POSTGRES_USER": f"{org_code}_user",
        "POSTGRES_PASSWORD": db_pass,
        "DATABASE_URL": f"postgresql+asyncpg://{org_code}_user:{db_pass}@db:5432/{org_code}_portal",
        "SECRET_KEY": secrets.token_hex(32),
        "SESSION_EXPIRE_MINUTES": "480",
        "LDAP_SERVER": cd["ldap_server"],
        "LDAP_PORT": "389",
        "LDAP_USE_SSL": "false",
        "LDAP_BASE_DN": cd["ldap_base_dn"],
        "LDAP_BIND_USER": cd["ldap_bind_user"],
        "LDAP_BIND_PASSWORD": cd["ldap_bind_password"],
        "LDAP_ADMIN_GROUP": cd["ldap_admin_group"],
        "LDAP_SSL_PORT": "636",
        "PASSWORD_MAX_AGE_DAYS": "90",
        "VPN_GROUP_ADMINS": cd.get("vpn_group_admins") or "",
        "VPN_GROUP_USERS": cd.get("vpn_group_users") or "",
        # Область синхронизации в Dominex (пусто = все пользователи/компьютеры)
        "SYNC_USER_GROUP": cd.get("sync_user_group") or "",
        "SYNC_COMPUTER_OU": cd.get("sync_computer_ou") or "",
        "OPNSENSE_HOST": cd.get("opnsense_host") or "",
        "OPNSENSE_API_KEY": cd.get("opnsense_api_key") or "",
        "OPNSENSE_API_SECRET": cd.get("opnsense_api_secret") or "",
        "OPNSENSE_VERIFY_SSL": "false",
        "OPNSENSE_CA_REF": cd.get("opnsense_ca_ref") or "",
        "OVPN_SERVER_ADMINS_UUID": cd.get("ovpn_server_admins_uuid") or "",
        "OVPN_SERVER_USERS_UUID": cd.get("ovpn_server_users_uuid") or "",
        "WG_SERVER_ADMINS_UUID": cd.get("wg_server_admins_uuid") or "",
        "WG_SERVER_USERS_UUID": cd.get("wg_server_users_uuid") or "",
        "WINRM_HOST": cd.get("winrm_host") or "",
        "WINRM_PORT": "5985",
        "WINRM_USER": cd.get("winrm_user") or "",
        "WINRM_PASSWORD": cd.get("winrm_password") or "",
        "PORTAL_TITLE": cd["portal_title"],
        "PORTAL_ORG_NAME": cd["portal_org_name"],
        "PORTAL_BASE_URL": cd["portal_base_url"],
        "MAIL_SYSTEMS_ENCRYPTION_KEY": Fernet.generate_key().decode(),
        # Интеграция с Dominex через SSOD Auth (M2M)
        "DOMINEX_API_BASE_URL": settings.ECOSYSTEM_DOMINEX_PUBLIC_URL,
        "DOMINEX_SOURCE_CODE": source_code,
        "SSOD_AUTH_BASE_URL": settings.ECOSYSTEM_SSOD_AUTH_PUBLIC_URL,
        "M2M_CLIENT_ID": f"{org_code}_portal",
        "M2M_CLIENT_SECRET": service_secret,
    }


@staff_member_required
def portal_deploy(request):
    """Форма + запуск авторазвёртывания портала на удалённой VM. Собирает
    SSH-реквизиты и конфиг, авто-регистрирует ServiceClient(+grant) и
    ExternalSource в Dominex, пишет spec-файл с секретами и запускает
    фоновый subprocess run_portal_deploy, редиректит на страницу статуса.
    SSH-креды в БД не сохраняются - только в spec-файле на время job."""
    if request.method != "POST":
        return render(request, "accounts/portal_deploy_form.html", {"form": PortalDeployForm()})

    form = PortalDeployForm(request.POST)
    if not form.is_valid():
        return render(request, "accounts/portal_deploy_form.html", {"form": form})

    cd = form.cleaned_data
    org = cd["org_code"]

    try:
        client, service_secret = _ensure_service_client(org)
        source_code = _ensure_dominex_source(org)
    except Exception as e:
        messages.error(request, f"Не удалось подготовить интеграции (ServiceClient/ExternalSource): {e}")
        return render(request, "accounts/portal_deploy_form.html", {"form": form})

    env_map = _build_portal_env(cd, org, service_secret, source_code)

    # Приоритет: SSH deploy-key (приватный репо) → HTTPS+токен → анонимный HTTPS.
    if settings.PORTAL_DEPLOY_SSH_KEY:
        clone = {
            "mode": "ssh",
            "url": settings.PORTAL_REPO_SSH_URL,
            "deploy_key": settings.PORTAL_DEPLOY_SSH_KEY,
        }
    elif settings.PORTAL_DEPLOY_TOKEN:
        token = settings.PORTAL_DEPLOY_TOKEN
        clone = {"mode": "https", "url": settings.PORTAL_REPO_URL.replace("https://", f"https://{token}@", 1)}
    else:
        clone = {"mode": "https", "url": settings.PORTAL_REPO_URL}

    job = DeployJob.objects.create(
        org_code=org,
        target_host=cd["target_host"],
        target_port=cd["target_port"],
        target_user=cd["target_user"],
        status=DeployJob.Status.PENDING,
        service_client=client,
        created_by=request.user,
    )

    spec = {
        "org_code": org,
        "clone": clone,
        "env": env_map,
        "ssh": {
            "password": cd.get("ssh_password") or "",
            "private_key": cd.get("ssh_private_key") or "",
            "key_passphrase": cd.get("ssh_key_passphrase") or "",
            "sudo_password": cd.get("sudo_password") or "",
        },
    }
    fd, spec_path = tempfile.mkstemp(prefix="deploy_", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(spec, fh)
    os.chmod(spec_path, 0o600)

    subprocess.Popen(
        [sys.executable, "manage.py", "run_portal_deploy", str(job.uuid), spec_path],
        cwd=str(settings.BASE_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    messages.success(request, f"Развёртывание портала «{org}» запущено.")
    return redirect("accounts:portal_deploy_status", job_uuid=job.uuid)


@staff_member_required
def portal_deploy_status(request, job_uuid):
    job = DeployJob.objects.filter(uuid=job_uuid).first()
    if job is None:
        raise Http404("Задача не найдена.")
    return render(request, "accounts/portal_deploy_status.html", {"job": job})


@staff_member_required
def portal_deploy_log(request, job_uuid):
    """JSON лог+статус для polling'а страницей статуса."""
    job = DeployJob.objects.filter(uuid=job_uuid).first()
    if job is None:
        raise Http404("Задача не найдена.")
    return JsonResponse({
        "status": job.status,
        "status_display": job.get_status_display(),
        "log": job.log,
        "finished": job.status in (DeployJob.Status.SUCCESS, DeployJob.Status.FAILED),
    })
