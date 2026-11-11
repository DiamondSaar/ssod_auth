"""
Аварийный сброс ключей входа пользователя (потерял все ключи).

    python manage.py reset_user_keys <логин>            — показать ключи
    python manage.py reset_user_keys <логин> --delete   — удалить все

После удаления администратор в мягком режиме войдёт паролем и добавит
новые ключи; в строгом режиме на это время переключить
ADMIN_SECOND_FACTOR=soft. Сброс пишется в журнал входов (AuthEvent).
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from django_otp_webauthn.models import WebAuthnCredential

from accounts.models import AuthEvent


class Command(BaseCommand):
    help = "Показать или удалить ключи входа (WebAuthn) пользователя."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("--delete", action="store_true", help="удалить все ключи пользователя")

    def handle(self, *args, **options):
        user = get_user_model().objects.filter(username=options["username"]).first()
        if user is None:
            raise CommandError(f"Пользователь «{options['username']}» не найден.")

        credentials = list(WebAuthnCredential.objects.filter(user=user).order_by("created_at"))
        for credential in credentials:
            last_used = f"{credential.last_used_at:%d.%m.%Y}" if credential.last_used_at else "—"
            self.stdout.write(
                f"{credential.pk}\t{credential.name or 'Ключ'}"
                f"\tдобавлен {credential.created_at:%d.%m.%Y}\tпоследний вход {last_used}"
            )
        if not credentials:
            self.stdout.write("Ключей нет.")
            return

        if not options["delete"]:
            return

        names = [c.name or "Ключ" for c in credentials]
        WebAuthnCredential.objects.filter(user=user).delete()
        AuthEvent.objects.create(
            user=user,
            event_type=AuthEvent.EventType.ACCESS_GRANTED,
            details={"webauthn_credentials_reset": names, "via": "manage.py reset_user_keys"},
        )
        self.stdout.write(self.style.WARNING(f"Удалено ключей: {len(names)}."))
