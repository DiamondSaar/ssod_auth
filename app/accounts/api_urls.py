from django.urls import path

from . import api, app_key


app_name = "accounts_api"

urlpatterns = [
    # Подпись аппаратным ключом из приложения Dominex (accounts/app_key.py).
    path("app-key/login/", app_key.api_login_begin, name="app_key_login"),
    path("app-key/<str:token>/", app_key.api_confirm_options, name="app_key_confirm_options"),
    path("app-key/<str:token>/complete/", app_key.api_complete, name="app_key_complete"),
    path("keys/verify/", api.verify_access_key, name="verify_access_key"),
    path("service-token/", api.issue_service_token, name="issue_service_token"),
    path("products/update/", api.admin_update_product, name="admin_update_product"),
    path("users/projection-changed/", api.dominex_projection_changed, name="dominex_projection_changed"),
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
