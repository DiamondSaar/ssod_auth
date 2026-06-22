from django.shortcuts import render


def home(request):
    return render(request, "main/home.html")


def services(request):
    return render(request, "main/services.html")


def products(request):
    return render(request, "main/products.html")


def contacts(request):
    return render(request, "main/contacts.html")