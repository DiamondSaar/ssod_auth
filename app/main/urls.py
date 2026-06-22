from django.urls import path

from . import views


app_name = "main"

urlpatterns = [
    path("", views.home, name="home"),
    path("services/", views.services, name="services"),
    path("products/", views.products, name="products"),
    path("contacts/", views.contacts, name="contacts"),
]
