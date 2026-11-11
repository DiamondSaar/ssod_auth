from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0016_customuser_is_organization_account"),
    ]

    operations = [
        migrations.AddField(
            model_name="customuser",
            name="dominex_role",
            field=models.CharField(blank=True, max_length=20, verbose_name="Роль в Dominex"),
        ),
    ]
