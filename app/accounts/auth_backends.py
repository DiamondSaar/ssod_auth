from django.contrib.auth import get_user_model
from django.contrib.auth.backends import BaseBackend

from accounts.services.dominex_client import fetch_user_projection, verify_dominex_credentials
from accounts.services.dominex_sync import apply_projection


class DominexCredentialBackend(BaseBackend):
    """Dominex is the sole store of ecosystem login credentials (see
    dominex/docs/module-interactions.md) - this backend replaces
    django.contrib.auth.backends.ModelBackend's local password check with
    a call to Dominex's /api/v1/identity/credentials/verify. ssod_auth
    never stores a real, checkable password locally once this is active
    (see accounts/auth_backends.py's DOMINEX_CREDENTIAL_BACKEND_ENABLED
    gate in settings.py for the local break-glass fallback).
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if not username or not password:
            return None

        result = verify_dominex_credentials(username, password)
        if not result or not result.get("valid"):
            return None

        User = get_user_model()
        user, created = User.objects.get_or_create(username=username)
        update_fields = []
        if created:
            # Never checked by this backend once created - Dominex is the
            # only place this user's real credential lives.
            user.set_unusable_password()
            update_fields.append("password")
        if user.must_change_password:
            # This field drives a *local* "change your password" form
            # (accounts/views.py::change_password) that writes to the same
            # dead local password field above - meaningless and actively
            # misleading once Dominex owns the real credential. Force it
            # off here (covers both brand-new users and any pre-existing
            # row still carrying the model's must_change_password=True
            # default from before this backend existed) rather than
            # relying on a one-off data migration.
            user.must_change_password = False
            update_fields.append("must_change_password")
        if update_fields:
            user.save(update_fields=update_fields)

        projection = fetch_user_projection(username)
        if projection:
            apply_projection(user, projection)

        return user

    def get_user(self, user_id):
        User = get_user_model()
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
