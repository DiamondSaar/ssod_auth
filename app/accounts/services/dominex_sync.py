"""Applies a Dominex identity/product-access projection (see
dominex_client.fetch_user_projection) to local SSOD Auth models.

Shared by the manual `sync_dominex_products` management command and the
live per-login refresh (accounts/signals.py) - one place for the upsert
logic so the two paths can't drift apart.

Deliberately does not touch first_name/last_name/middle_name - Dominex's
projection only has one combined display_name string, splitting that into
name parts is lossy and out of scope; ФИО stays SSOD-Auth-owned for now.
"""

from django.utils import timezone

from accounts.models import Organization, Position, Product, ProductRole, UserProductAccess

DOMINEX_SYNC_ROLE_CODE = "dominex_sync"


def apply_projection(user, projection):
    """Upserts CustomUser.organization/.position/.access_class and
    UserProductAccess grants from one Dominex projection dict. Caller is
    responsible for fetching the projection and deciding what to do on
    None (this function assumes a real dict)."""
    summary = {"organization": None, "position": None, "grants_synced": 0}

    access_class = projection.get("access_class")
    if access_class:
        user.access_class = access_class

    position_name = projection.get("position")
    if position_name:
        position, _ = Position.objects.get_or_create(name=position_name)
        user.position = position
        summary["position"] = position_name

    org_data = projection.get("organization")
    if not org_data:
        # UserProductAccess.organization is a required FK (on_delete=PROTECT,
        # not nullable) - nothing to attach grants to without one, but the
        # access_class/position updates above still apply.
        user.save()
        return summary

    organization, _ = Organization.objects.get_or_create(
        name=org_data["name"],
        defaults={"inn": org_data.get("inn") or ""},
    )
    user.organization = organization
    summary["organization"] = organization.name
    user.save()

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
        summary["grants_synced"] += 1

    return summary
