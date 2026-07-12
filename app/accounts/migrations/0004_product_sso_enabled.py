# Generated manually, mirroring the style of 0003_userproductaccess_dominex_grant_id_and_more.py

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_userproductaccess_dominex_grant_id_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='sso_enabled',
            field=models.BooleanField(default=False, help_text='Если включено, кнопка запуска продукта выдаёт подписанный SSO-тикет вместо прямого перехода по product_url (см. dominex/docs/module-interactions.md).', verbose_name='SSO-тикет'),
        ),
    ]
