"""
Подключение кабинета юридического лица.

Порядок для новой организации:

1. В Dominex завести обезличенную учётную запись (например `spa-lk`)
   и привязать её к нужной организации — Dominex хранит пароли и является
   источником истины по организациям.
2. Выполнить эту команду: она заводит локальную запись в кабинете,
   подтягивает организацию из Dominex и включает режим кабинета юрлица.

    python manage.py setup_org_account --username ascom-lk
    python manage.py setup_org_account --username spa-lk --off   # выключить режим
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from accounts.services.dominex_client import fetch_user_projection
from accounts.services.dominex_sync import apply_projection


class Command(BaseCommand):
    help = "Включает режим кабинета юридического лица для обезличенной учётной записи."

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True, help="Логин учётной записи в Dominex")
        parser.add_argument(
            "--off",
            action="store_true",
            help="Выключить режим кабинета юрлица (запись станет обычной).",
        )

    def handle(self, *args, **options):
        User = get_user_model()
        username = options["username"].strip()

        user, created = User.objects.get_or_create(username=username)

        if created:
            # Пароль живёт в Dominex, локальный проверять нечем.
            user.set_unusable_password()
            user.must_change_password = False
            user.save(update_fields=["password", "must_change_password"])
            self.stdout.write(f"создана локальная запись: {username}")

        projection = fetch_user_projection(username)

        if projection is None:
            if created:
                user.delete()
                raise CommandError(
                    f"Dominex не знает учётную запись «{username}». "
                    "Сначала заведите её в Dominex и привяжите к организации."
                )
            self.stdout.write(self.style.WARNING(
                "Dominex не ответил — организация не обновлена, режим переключаю по существующим данным."
            ))
        else:
            summary = apply_projection(user, projection)
            self.stdout.write(f"организация из Dominex: {summary.get('organization') or '—'}")

        user.refresh_from_db()

        if options["off"]:
            user.is_organization_account = False
            user.save(update_fields=["is_organization_account"])
            self.stdout.write(self.style.SUCCESS(f"{username}: режим кабинета юрлица выключен"))
            return

        if user.organization is None:
            raise CommandError(
                f"У «{username}» не определена организация. Привяжите учётную запись "
                "к организации в Dominex и повторите команду."
            )

        user.is_organization_account = True
        user.save(update_fields=["is_organization_account"])

        self.stdout.write(self.style.SUCCESS(
            f"{username}: кабинет юрлица включён, организация «{user.organization.name}». "
            "Вход — https://auth.ssod.pro/account/login/, дальше открывается /account/org/."
        ))
