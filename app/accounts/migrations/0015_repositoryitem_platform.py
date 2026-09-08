"""Платформа сборки в карточке репозитория.

Карточка была написана в расчёте на мобильные приложения: QR-код и
подсказка «отсканируйте камерой телефона». Для настольного клиента
(Dominex Vox под Windows) это вводит в заблуждение — файл нужно
скачивать на компьютер. Поле определяет, как показывать карточку.

По умолчанию android, потому что все существующие записи (Biographia,
DomineX-Scaner) — мобильные.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0014_customuser_infrastructure_access_override"),
    ]

    operations = [
        migrations.AddField(
            model_name="repositoryitem",
            name="platform",
            field=models.CharField(
                choices=[
                    ("android", "Android"),
                    ("windows", "Windows"),
                    ("ios", "iOS"),
                    ("other", "Другое"),
                ],
                default="android",
                help_text=(
                    "Определяет, как показывать карточку: для мобильных — QR-код "
                    "и подсказка «отсканируйте телефоном», для настольных — "
                    "предупреждение, что файл нужно скачивать на компьютер."
                ),
                max_length=16,
                verbose_name="Платформа",
            ),
        ),
    ]
