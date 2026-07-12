from django.contrib.auth.hashers import make_password
from django.db import migrations


def make_non_superuser_passwords_unusable(apps, schema_editor):
    # Dominex becomes the sole store of credentials from here on - local
    # password hashes on non-superuser accounts are pure leftovers from
    # before this migration (no real production users yet, confirmed with
    # the user). Superuser passwords are deliberately left untouched - see
    # DOMINEX_CREDENTIAL_BACKEND_ENABLED in settings.py, that local hash is
    # the break-glass rollback path.
    User = apps.get_model('accounts', 'CustomUser')
    for user in User.objects.filter(is_superuser=False):
        # make_password(None) is the same "!<random>" unusable-password
        # marker set_unusable_password() would produce - can't call the
        # real model method from a historical migration model.
        user.password = make_password(None)
        user.save(update_fields=['password'])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_enable_dominex_sso'),
    ]

    operations = [
        migrations.RunPython(make_non_superuser_passwords_unusable, noop),
    ]
