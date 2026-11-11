"""
Посредник, который держит обезличенную учётную запись организации
в её собственной зоне — /account/org/.

Зачем отдельный слой, а не проверка в каждой вьюхе: личных разделов
в кабинете много (продукты, ключи, репозиторий, безопасность), и любой
забытый становится дырой в разделении. Здесь правило одно и общее:
учётка юрлица ходит только по своей зоне, всё остальное в /account/
возвращает её на её же страницу.
"""

from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import logout
from django.http import JsonResponse
from django.shortcuts import redirect

from accounts import second_factor


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


# Адреса, без которых не пройти подтверждение ключом (или не уйти).
KEY_CHECK_ALLOWED = (
    "/account/login/",
    "/account/logout/",
    "/webauthn/authentication/",
    "/webauthn/jsi18n/",
    "/static/",
    "/favicon.ico",
)


class AdminSecondFactorMiddleware:
    """
    Администратор, вошедший только паролем, дальше страницы подтверждения
    ключом не проходит (accounts/second_factor.py — правило и режимы).

    Стоит после OTPMiddleware: тот выставляет request.user.is_verified().
    Служебное API (/api/...) не трогаем — там вход по сервисным токенам,
    а не по сессии человека.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.second_factor_missing_key = False
        user = getattr(request, "user", None)

        if (
            user is None
            or not user.is_authenticated
            or second_factor.mode() == second_factor.MODE_OFF
            or not second_factor.requires_key(user)
            or second_factor.is_key_verified(request)
            or request.path.startswith("/api/")
        ):
            return self.get_response(request)

        if request.path.startswith(KEY_CHECK_ALLOWED):
            return self.get_response(request)

        if second_factor.user_keys(user).exists():
            # Ключ есть — подтверди им вход. Вернём туда, куда шёл.
            query = urlencode({"next": request.get_full_path()})
            if request.headers.get("Accept", "").startswith("application/json"):
                return JsonResponse({"error": "second_factor_required"}, status=403)
            return redirect(f"/account/login/key/?{query}")

        if second_factor.mode() == second_factor.MODE_STRICT:
            logout(request)
            messages.error(
                request,
                "Администраторам вход только с аппаратным ключом, а ключ для "
                "вашей учётной записи не зарегистрирован. Обратитесь к суперадминистратору.",
            )
            return redirect("accounts:login")

        # Мягкий режим, ключа ещё нет: пускаем, страницы покажут просьбу.
        request.second_factor_missing_key = True
        return self.get_response(request)
