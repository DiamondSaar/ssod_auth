from django.core.management.base import BaseCommand

from accounts.models import CustomUser
from accounts.services.dominex_client import fetch_user_projection
from accounts.services.dominex_sync import apply_projection


class Command(BaseCommand):
    help = (
        "Pulls each user's identity/product-access projection from Dominex Core "
        "and upserts local CustomUser.organization/.position/.access_class plus "
        "Product/UserProductAccess rows as a cache/projection (see "
        "dominex/docs/module-interactions.md). Does not touch credentials, "
        "passkeys or sessions - those stay owned by SSOD Auth. Same upsert logic "
        "also runs live on every login (accounts/signals.py) - this command is "
        "for bulk/manual warming, e.g. users who haven't logged in in a while."
    )

    def handle(self, *args, **options):
        synced_users = 0
        synced_grants = 0

        for user in CustomUser.objects.all():
            projection = fetch_user_projection(user.username)
            if projection is None:
                continue
            synced_users += 1
            summary = apply_projection(user, projection)
            synced_grants += summary["grants_synced"]

        self.stdout.write(
            self.style.SUCCESS(
                f"Synced {synced_grants} product access grant(s) for {synced_users} user(s)."
            )
        )
