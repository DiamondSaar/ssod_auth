"""
Отправка сообщения из кабинета юрлица в мессенджер Dominex Vox.

Канал поддержки принимает сообщения через входящую интеграцию Vox:
её адрес лежит в настройке VOX_SUPPORT_WEBHOOK_URL и больше ничего
не требует — учётная запись Vox клиенту не нужна.

Функция никогда не бросает исключение: связь с клиентом не должна
падать из-за недоступного мессенджера. О неудаче сообщаем возвратом
False, письмо остаётся запасным каналом.
"""

import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 5


def send_support_message(organization_name, author, text, contact=""):
    """
    Кладёт сообщение в канал поддержки Vox.

    organization_name — от чьего имени пришло обращение;
    author — кто написал (имя из формы);
    contact — как ответить (почта или телефон), может быть пустым.
    """
    webhook_url = getattr(settings, "VOX_SUPPORT_WEBHOOK_URL", "")

    if not webhook_url:
        logger.warning("VOX_SUPPORT_WEBHOOK_URL не задан — сообщение в Vox не отправлено")
        return False

    header = ["*Обращение из кабинета юрлица: {}*".format(organization_name)]

    if author:
        header.append("Автор: {}".format(author))
    if contact:
        header.append("Обратная связь: {}".format(contact))

    payload = {"text": "\n".join(header) + "\n\n" + text.strip()}

    try:
        response = requests.post(webhook_url, json=payload, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
    except Exception:
        logger.warning("Не удалось отправить сообщение в Vox", exc_info=True)
        return False

    return True
