from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0015_repositoryitem_platform"),
    ]

    operations = [
        migrations.AddField(
            model_name="customuser",
            name="is_organization_account",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Обезличенная учётная запись организации: вместо личного кабинета "
                    "открывается кабинет юрлица (/account/org/) с мониторингом, "
                    "документами и связью. Личные разделы такой учётке недоступны."
                ),
                verbose_name="Кабинет юридического лица",
            ),
        ),
    ]
