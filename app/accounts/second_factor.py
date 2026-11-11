"""
Второй фактор (аппаратный ключ, WebAuthn) для администраторов.

Правило владельца (11.11.2026): админский доступ всегда защищён ключом,
пользователи без админских прав входят по логину и паролю.

Кто «администратор»: роль admin/superadmin в Dominex (приходит с
проекцией, CustomUser.dominex_role) или сотрудник Django-админки
SSOD Auth (is_staff/is_superuser).

«Вход подтверждён ключом» = request.user.is_verified() из django_otp:
его выставляет django_otp_webauthn и при входе ключом вместо пароля
(там обязателен PIN), и при подтверждении ключом после пароля.

Режимы — settings.ADMIN_SECOND_FACTOR:
- off    — проверки нет (аварийный выход, переключается в .env);
- soft   — у кого ключ есть, тот обязан им подтвердить вход; у кого
           нет — пускаем, но на каждой странице просим добавить ключ;
- strict — без подтверждения ключом админа не пускаем вовсе.
"""

from django.conf import settings

from django_otp_webauthn.models import WebAuthnCredential


MODE_OFF = "off"
MODE_SOFT = "soft"
MODE_STRICT = "strict"

ADMIN_ROLES = {"admin", "superadmin"}

# Отметки способа входа для билетов в продукты (поле amr, RFC 8176):
# pwd — пароль, hwk — аппаратный ключ.
AMR_PASSWORD = "pwd"
AMR_HARDWARE_KEY = "hwk"


def mode():
    value = getattr(settings, "ADMIN_SECOND_FACTOR", MODE_SOFT)
    return value if value in (MODE_OFF, MODE_SOFT, MODE_STRICT) else MODE_STRICT


def requires_key(user):
    return bool(
        user.is_staff
        or user.is_superuser
        or (getattr(user, "dominex_role", "") or "").lower() in ADMIN_ROLES
    )


def user_keys(user):
    return WebAuthnCredential.objects.filter(user=user, confirmed=True)


def is_key_verified(request):
    is_verified = getattr(request.user, "is_verified", None)
    return bool(is_verified and is_verified())


def login_amr(request):
    """Чем подтверждён текущий вход — для билета в продукт."""
    if is_key_verified(request):
        return [AMR_HARDWARE_KEY]
    return [AMR_PASSWORD]
