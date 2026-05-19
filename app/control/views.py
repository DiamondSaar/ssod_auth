from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import get_user_model
from django.db.models import Exists, OuterRef
from django.shortcuts import render

from django.contrib import messages
from django.shortcuts import redirect

from accounts.services.email_service import send_user_created_email
from .forms import UserCreateForm


from accounts.models import SSODAccessKey


@staff_member_required
def dashboard(request):
    """
    Главная страница панели управления Auth Center.
    """

    cards = [
        {
            "title": "Пользователи",
            "description": "Учетные записи, статусы, классы доступа и ключи ССОД.",
            "url": "/manage/users/",
        },
        {
            "title": "Организации",
            "description": "Справочник юридических лиц и организаций.",
            "url": "#",
        },
        {
            "title": "Продукты",
            "description": "Dominex, FinSoft, Личный кабинет и другие сервисы.",
            "url": "#",
        },
        {
            "title": "Роли и права",
            "description": "Наборы прав доступа для продуктов ССОД.",
            "url": "/account/roles-rights/",
        },
        {
            "title": "Доступы",
            "description": "Кто, к какому продукту и от какой организации имеет доступ.",
            "url": "#",
        },
        {
            "title": "Ключи ССОД",
            "description": "Выпуск, отзыв и контроль ключей доступа.",
            "url": "#",
        },
        {
            "title": "Журнал событий",
            "description": "Входы, ошибки авторизации и проверки доступа.",
            "url": "#",
        },
    ]

    return render(request, "control/dashboard.html", {"cards": cards})


@staff_member_required
def user_list(request):
    """
    Список пользователей Auth Center.

    Здесь делаем свой рабочий интерфейс вместо Django Admin:
    - таблица;
    - поиск;
    - фильтры;
    - быстрый просмотр статуса;
    - признак наличия активного ключа ССОД.
    """

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
        users = users.filter(
            username__icontains=query
        ) | users.filter(
            last_name__icontains=query
        ) | users.filter(
            first_name__icontains=query
        ) | users.filter(
            middle_name__icontains=query
        )

    if status == "active":
        users = users.filter(is_active=True)

    if status == "blocked":
        users = users.filter(is_active=False)

    if access_class:
        users = users.filter(access_class=access_class)

    return render(
        request,
        "control/user_list.html",
        {
            "users": users,
            "query": query,
            "status": status,
            "access_class": access_class,
            "access_classes": User._meta.get_field("access_class").choices,
        },
    )


@staff_member_required
def user_create(request):
    """
    Создание пользователя через рабочую панель Auth Center.

    После сохранения:
    - создаем пользователя;
    - отправляем письмо с временным паролем;
    - возвращаем админа в список пользователей.
    """

    if request.method == "POST":
        form = UserCreateForm(request.POST)

        if form.is_valid():
            user = form.save()

            send_user_created_email(
                user=user,
                temporary_password=form.generated_password,
            )

            messages.success(
                request,
                f"Пользователь {user.username} создан. Письмо отправлено на {user.email}.",
            )

            return redirect("control:user_list")

    else:
        form = UserCreateForm()

    return render(
        request,
        "control/user_form.html",
        {
            "form": form,
            "page_title": "Создание пользователя",
        },
    )
