import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def fetch_user_projection(username):
    """Fetch the identity + product-access projection for one user from
    Dominex Core (see dominex/docs/module-interactions.md).

    Best-effort only - this is a sync/cache path, not part of the live
    login flow, so any failure (connection error, non-200, bad JSON) is
    logged and returns None rather than raising.
    """

    url = f"{settings.DOMINEX_API_BASE_URL}/api/v1/identity/projection/users/{username}"
    try:
        response = requests.get(
            url,
            headers={"X-Dominex-Api-Key": settings.DOMINEX_API_KEY},
            timeout=5,
        )
    except requests.RequestException:
        logger.warning("Dominex projection request failed for %s", username, exc_info=True)
        return None

    if response.status_code != 200:
        logger.warning(
            "Dominex projection for %s returned %s", username, response.status_code
        )
        return None

    try:
        return response.json()
    except ValueError:
        logger.warning("Dominex projection for %s returned invalid JSON", username, exc_info=True)
        return None
