from django.contrib.auth import views as auth_views
from django.urls import path

from . import views


app_name = "accounts"

urlpatterns = [
    path("", views.account_home, name="account_home"),
    path("change-password/", views.change_password, name="change_password"),
    path("keys/", views.access_key_list, name="access_key_list"),
    path("keys/create/", views.access_key_create, name="access_key_create"),
    path("keys/<uuid:key_uuid>/revoke/", views.access_key_revoke, name="access_key_revoke"),
    path("security/", views.security, name="security"),
    path(
        "products/",
        views.account_products,
        name="account_products",

    ),

    path(
        "sso/authorize/<slug:product_code>/",
        views.sso_authorize,
        name="sso_authorize",
    ),

    path(
        "login/",
        auth_views.LoginView.as_view(
            template_name="accounts/login.html",
            redirect_authenticated_user=True,
        ),
        name="login",
    ),

    path(
        "logout/",
        auth_views.LogoutView.as_view(),
        name="logout",
    ),



    path(
        "roles-rights/",
        views.roles_rights,
        name="roles_rights",
    ),

]
