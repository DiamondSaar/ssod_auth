from django.shortcuts import redirect


def home(request):
    return redirect("https://ssod.pro/", permanent=True)


def services(request):
    return redirect("https://ssod.pro/services/", permanent=True)


def products(request):
    return redirect("https://ssod.pro/products/", permanent=True)


def contacts(request):
    return redirect("https://ssod.pro/contacts/", permanent=True)
