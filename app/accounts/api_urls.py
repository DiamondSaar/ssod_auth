from django.urls import path

from . import api


app_name = "accounts_api"

urlpatterns = [
    path("keys/verify/", api.verify_access_key, name="verify_access_key"),
]
