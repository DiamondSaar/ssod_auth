from django.shortcuts import render


def home(request):
    """
    Главная страница SSOD Auth Center.

    Это публичная стартовая страница сервиса авторизации.
    Позже отсюда будут доступны:
    - вход пользователя;
    - личный кабинет;
    - выпуск Ключа доступа ССОД;
    - управление привязанными ключами.
    """
    return render(request, "main/home.html")
