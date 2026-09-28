"""
Посредник, который держит обезличенную учётную запись организации
в её собственной зоне — /account/org/.

Зачем отдельный слой, а не проверка в каждой вьюхе: личных разделов
в кабинете много (продукты, ключи, репозиторий, безопасность), и любой
забытый становится дырой в разделении. Здесь правило одно и общее:
учётка юрлица ходит только по своей зоне, всё остальное в /account/
возвращает её на её же страницу.
"""

from django.shortcuts import redirect


# Зона кабинета юрлица и служебные адреса, которые нужны всем.
ORG_PREFIX = "/account/org/"

ALWAYS_ALLOWED = (
    "/account/login/",
    "/account/logout/",
)


class OrganizationCabinetMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)

        if (
            user is not None
            and user.is_authenticated
            and getattr(user, "is_organization_account", False)
            and not user.is_staff
        ):
            path = request.path

            if (
                path.startswith("/account/")
                and not path.startswith(ORG_PREFIX)
                and not path.startswith(ALWAYS_ALLOWED)
            ):
                return redirect("accounts:org_home")

        return self.get_response(request)
