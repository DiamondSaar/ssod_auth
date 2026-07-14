from django.urls import path

from . import api


app_name = "accounts_api"

urlpatterns = [
    path("keys/verify/", api.verify_access_key, name="verify_access_key"),
    path("products/update/", api.admin_update_product, name="admin_update_product"),
    path("personal-key/", api.store_personal_key_material, name="store_personal_key_material"),
    path("personal-key/<str:username>/", api.fetch_personal_key_material, name="fetch_personal_key_material"),
    path("webauthn-credentials/", api.store_webauthn_credential, name="store_webauthn_credential"),
    path(
        "webauthn-credentials/<str:username>/",
        api.fetch_webauthn_credentials,
        name="fetch_webauthn_credentials",
    ),
    path(
        "webauthn-credentials/<str:credential_id>/sign-count/",
        api.update_webauthn_sign_count,
        name="update_webauthn_sign_count",
    ),
]
