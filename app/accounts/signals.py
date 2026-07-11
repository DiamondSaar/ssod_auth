import logging

from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

from accounts.services.dominex_client import fetch_user_projection
from accounts.services.dominex_sync import apply_projection

logger = logging.getLogger(__name__)

# Shorter than the management command's default (5s) - this now runs on
# every interactive login, not a background batch job.
LOGIN_SYNC_TIMEOUT = 2


@receiver(user_logged_in)
def refresh_dominex_projection(sender, request, user, **kwargs):
    """Best-effort live refresh of organization/position/access_class and
    product grants from Dominex, on every login - password and passkey
    both fire this signal via django.contrib.auth.login(), so this covers
    both without touching either AUTHENTICATION_BACKENDS entry. Never
    raises - a Dominex outage must not block login."""
    try:
        projection = fetch_user_projection(user.username, timeout=LOGIN_SYNC_TIMEOUT)
        if projection is not None:
            apply_projection(user, projection)
    except Exception:
        logger.warning("Dominex live projection sync failed for %s", user.username, exc_info=True)
