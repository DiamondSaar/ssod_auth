from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import CustomUser, Organization, Product, ProductRole, UserProductAccess
from accounts.services.dominex_client import fetch_user_projection

DOMINEX_SYNC_ROLE_CODE = "dominex_sync"


class Command(BaseCommand):
    help = (
        "Pulls each user's identity/product-access projection from Dominex Core "
        "and upserts local Product/UserProductAccess rows as a cache/projection "
        "(see dominex/docs/module-interactions.md). Does not touch credentials, "
        "passkeys or sessions - those stay owned by SSOD Auth."
    )

    def handle(self, *args, **options):
        synced_users = 0
        synced_grants = 0

        for user in CustomUser.objects.all():
            projection = fetch_user_projection(user.username)
            if projection is None:
                continue
            synced_users += 1

            org_data = projection.get("organization")
            if not org_data:
                # UserProductAccess.organization is a required FK (on_delete=PROTECT,
                # not nullable) - nothing to attach these grants to without one.
                continue
            organization, _ = Organization.objects.get_or_create(
                name=org_data["name"],
                defaults={"inn": org_data.get("inn") or ""},
            )

            for product_data in projection.get("products", []):
                product, _ = Product.objects.get_or_create(
                    code=product_data["code"],
                    defaults={"name": product_data["name"]},
                )
                role, _ = ProductRole.objects.get_or_create(
                    product=product,
                    code=DOMINEX_SYNC_ROLE_CODE,
                    defaults={"name": "Синхронизировано из Dominex"},
                )
                UserProductAccess.objects.update_or_create(
                    user=user,
                    product=product,
                    defaults={
                        "organization": organization,
                        "role": role,
                        "access_class": product_data.get("access_class") or "G",
                        "status": product_data.get("status") or UserProductAccess.Status.ACTIVE,
                        "dominex_grant_id": product_data.get("grant_id"),
                        "synced_at": timezone.now(),
                    },
                )
                synced_grants += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Synced {synced_grants} product access grant(s) for {synced_users} user(s)."
            )
        )
