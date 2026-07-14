# Generated manually, mirroring the style of 0004_product_sso_enabled.py

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0006_local_passwords_unusable'),
    ]

    operations = [
        migrations.AlterField(
            model_name='authevent',
            name='event_type',
            field=models.CharField(
                choices=[
                    ('login_success', 'Успешный вход'),
                    ('login_failed', 'Неуспешный вход'),
                    ('logout', 'Выход'),
                    ('key_login_success', 'Вход по ключу успешен'),
                    ('key_login_failed', 'Вход по ключу неуспешен'),
                    ('access_denied', 'Доступ запрещен'),
                    ('access_granted', 'Доступ разрешен'),
                    ('product_config_synced', 'Конфигурация продукта синхронизирована из Dominex'),
                ],
                max_length=50,
                verbose_name='Тип события',
            ),
        ),
    ]
