from django.db import migrations


def enable_dominex_sso(apps, schema_editor):
    # Only touches the row if it already exists - product_url differs per
    # environment (dev vs prod) and isn't something this migration should
    # guess at by creating a new row.
    Product = apps.get_model('accounts', 'Product')
    Product.objects.filter(code='dominex').update(sso_enabled=True)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0004_product_sso_enabled'),
    ]

    operations = [
        migrations.RunPython(enable_dominex_sso, noop),
    ]
