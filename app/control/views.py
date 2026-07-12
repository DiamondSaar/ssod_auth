from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import get_user_model
from django.contrib import messages
from django.db.models import Exists, OuterRef
from django.shortcuts import get_object_or_404, redirect, render

from accounts.models import SSODAccessKey, Product, UserProductAccess
from accounts.services.email_service import send_user_created_email
from .forms import UserCreateForm, UserEditForm


@staff_member_required
def dashboard(request):
    """
    Legacy SSOD Auth management dashboard.

    Master-data management is moving to Dominex Core. Keep this route as a
    compatibility bridge so old /manage/ links do not expose a second admin
    console or create conflicting ownership.
    """
    return redirect(settings.DOMINEX_CORE_CONSOLE_URL)


@staff_member_required
def user_list(request):
    if settings.DOMINEX_CONNECTED_MODE:
        return redirect(settings.DOMINEX_CORE_CONSOLE_URL)

    User = get_user_model()
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    access_class = request.GET.get("access_class", "").strip()

    active_key_subquery = SSODAccessKey.objects.filter(
        user=OuterRef("pk"),
        status=SSODAccessKey.Status.ACTIVE,
    )

    users = (
        User.objects.select_related("organization", "position")
        .annotate(has_active_ssod_key=Exists(active_key_subquery))
        .order_by("last_name", "first_name", "username")
    )

    if query:
        users = (
            users.filter(username__icontains=query)
            | users.filter(last_name__icontains=query)
            | users.filter(first_name__icontains=query)
            | users.filter(middle_name__icontains=query)
        )

    if status == "active":
        users = users.filter(is_active=True)
    elif status == "blocked":
        users = users.filter(is_active=False)

    if access_class:
        users = users.filter(access_class=access_class)

    return render(request, "control/user_list.html", {
        "users": users,
        "query": query,
        "status": status,
        "access_class": access_class,
        "access_classes": User._meta.get_field("access_class").choices,
    })


@staff_member_required
def user_create(request):
    """
    Создание нового пользователя.
    После сохранения отправляем письмо с временным паролем.
    """
    if settings.DOMINEX_CONNECTED_MODE:
        return redirect(settings.DOMINEX_CORE_CONSOLE_URL)

    if request.method == "POST":
        form = UserCreateForm(request.POST)
        if form.is_valid():
            user = form.save()
            send_user_created_email(user=user, temporary_password=form.generated_password)
            messages.success(request, f"Пользователь {user.username} создан. Письмо отправлено на {user.email}.")
            return redirect("control:user_detail", uuid=user.uuid)
    else:
        form = UserCreateForm()

    return render(request, "control/user_form.html", {
        "form": form,
        "page_title": "Новый пользователь",
        "is_create": True,
    })


@staff_member_required
def user_detail(request, uuid):
    """
    Карточка пользователя.

    GET             — режим просмотра
    GET ?edit=1     — режим редактирования
    POST            — сохранение изменений
    POST ?action=reset_password — сброс пароля
    """
    if settings.DOMINEX_CONNECTED_MODE:
        return redirect(settings.DOMINEX_CORE_CONSOLE_URL)

    User = get_user_model()
    user = get_object_or_404(User, uuid=uuid)

    # --- Сброс пароля ---
    if request.method == "POST" and request.POST.get("action") == "reset_password":
        from control.forms import generate_temporary_password
        from accounts.services.email_service import send_user_created_email

        new_password = generate_temporary_password()
        user.set_password(new_password)
        user.must_change_password = True
        user.save(update_fields=["password", "must_change_password"])
        send_user_created_email(user=user, temporary_password=new_password)
        messages.success(request, f"Пароль сброшен. Новый временный пароль отправлен на {user.email}.")
        return redirect("control:user_detail", uuid=uuid)

    # --- Сохранение редактирования ---
    if request.method == "POST":
        form = UserEditForm(request.POST, request.FILES, instance=user)
        if form.is_valid():
            form.save()

            # --- Сохраняем почты ---
            from accounts.models import UserEmail
            UserEmail.objects.filter(user=user).delete()
            i = 0
            while True:
                email_val = request.POST.get(f"email_{i}", "").strip()
                if not email_val:
                    i += 1
                    if i > 20:
                        break
                    continue
                comment_val = request.POST.get(f"email_comment_{i}", "").strip()
                UserEmail.objects.create(
                    user=user,
                    email=email_val,
                    comment=comment_val,
                    is_primary=(i == 0),
                )
                i += 1
                if i > 20:
                    break

            # --- Сохраняем телефоны ---
            from accounts.models import UserPhone
            UserPhone.objects.filter(user=user).delete()
            i = 0
            while True:
                phone_val = request.POST.get(f"phone_{i}", "").strip()
                if not phone_val:
                    i += 1
                    if i > 20:
                        break
                    continue
                code_val = request.POST.get(f"phone_code_{i}", "+7").strip()
                comment_val = request.POST.get(f"phone_comment_{i}", "").strip()
                UserPhone.objects.create(
                    user=user,
                    country_code=code_val,
                    number=phone_val,
                    comment=comment_val,
                    is_primary=(i == 0),
                )
                i += 1
                if i > 20:
                    break

            messages.success(request, "Данные пользователя сохранены.")
            return redirect("control:user_detail", uuid=uuid)
        edit_mode = True
    else:
        form = UserEditForm(instance=user)
        edit_mode = request.GET.get("edit") == "1"

    # Продукты для таблицы доступов
    products = Product.objects.filter(is_active=True).order_by("sort_order", "code")
    accesses = UserProductAccess.objects.filter(user=user).select_related("product", "role")
    access_map = {a.product_id: a for a in accesses}

    product_rows = []
    for product in products:
        access = access_map.get(product.id)
        product_rows.append({
            "product": product,
            "access": access,
            "is_active": access.is_currently_active() if access else False,
        })

    return render(request, "control/user_detail.html", {
        "viewed_user": user,
        "form": form,
        "edit_mode": edit_mode,
        "product_rows": product_rows,
    })