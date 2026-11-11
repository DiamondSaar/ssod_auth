import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0017_customuser_dominex_role"),
        ("django_otp_webauthn", "0004_webauthnuserhandle"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AppKeyFlow",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("token", models.CharField(max_length=64, unique=True, verbose_name="Токен запроса")),
                ("purpose", models.CharField(choices=[("login", "Вход в приложение"), ("confirm", "Подтверждение входа в браузере")], max_length=16, verbose_name="Назначение")),
                ("state", models.JSONField(blank=True, default=dict, verbose_name="Состояние проверки")),
                ("browser_session_hash", models.CharField(blank=True, max_length=64, verbose_name="Сессия браузера (хеш)")),
                ("browser_ip", models.GenericIPAddressField(blank=True, null=True, verbose_name="IP браузера")),
                ("browser_agent", models.TextField(blank=True, verbose_name="Браузер")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Создан")),
                ("expires_at", models.DateTimeField(verbose_name="Истекает")),
                ("completed_at", models.DateTimeField(blank=True, null=True, verbose_name="Подписан ключом")),
                ("consumed_at", models.DateTimeField(blank=True, null=True, verbose_name="Использован")),
                ("device", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="django_otp_webauthn.webauthncredential", verbose_name="Ключ")),
                ("product", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to="accounts.product", verbose_name="Продукт (билет при входе)")),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="app_key_flows", to=settings.AUTH_USER_MODEL, verbose_name="Пользователь")),
            ],
            options={
                "verbose_name": "Запрос подписи ключом из приложения",
                "verbose_name_plural": "Запросы подписи ключом из приложения",
            },
        ),
    ]
