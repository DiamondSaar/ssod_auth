import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def fetch_user_projection(username, timeout=5):
    """Fetch the identity + product-access projection for one user from
    Dominex Core (see dominex/docs/module-interactions.md).

    Best-effort only - any failure (connection error, non-200, bad JSON)
    is logged and returns None rather than raising. Called both from the
    manual sync_dominex_products command (default 5s timeout is fine) and
    from the live per-login refresh (accounts/signals.py passes a shorter
    timeout - this call is now in the interactive login path).
    """

    url = f"{settings.DOMINEX_API_BASE_URL}/api/v1/identity/projection/users/{username}"
    try:
        response = requests.get(
            url,
            headers={"X-Dominex-Api-Key": settings.DOMINEX_API_KEY},
            timeout=timeout,
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


def verify_dominex_credentials(username, password, timeout=5):
    """Verify a username/password pair against Dominex - the sole store of
    ecosystem login credentials (see docs/module-interactions.md). ssod_auth
    never sees or stores a real password hash, only this pass/fail verdict.

    Same never-raise, log-and-return-None-on-any-failure style as
    fetch_user_projection() above - callers must treat None the same as a
    failed verification (fail closed), not as "unknown, let them in".
    """

    url = f"{settings.DOMINEX_API_BASE_URL}/api/v1/identity/credentials/verify"
    try:
        response = requests.post(
            url,
            json={"username": username, "password": password},
            headers={"X-Dominex-Api-Key": settings.DOMINEX_API_KEY},
            timeout=timeout,
        )
    except requests.RequestException:
        logger.warning("Dominex credential verification request failed for %s", username, exc_info=True)
        return None

    if response.status_code != 200:
        logger.warning(
            "Dominex credential verification for %s returned %s", username, response.status_code
        )
        return None

    try:
        return response.json()
    except ValueError:
        logger.warning("Dominex credential verification for %s returned invalid JSON", username, exc_info=True)
        return None
