from django.urls import path
from . import views

app_name = "control"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("users/", views.user_list, name="user_list"),
    path("users/create/", views.user_create, name="user_create"),
    path("users/<uuid:uuid>/", views.user_detail, name="user_detail"),
]