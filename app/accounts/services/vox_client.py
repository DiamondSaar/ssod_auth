"""
Отправка обращения из кабинета юрлица в мессенджер Dominex Vox.

Пишем служебной учётной записью прямо в канал поддержки по его
идентификатору (chat.postMessage). Входящая интеграция («вебхук») для
этого не годится: Vox не принимает в ней канал с русским названием —
«поддержка» он не находит, а идентификатор комнаты в этом поле
не принимает вовсе.

Функция никогда не бросает исключение: связь с клиентом не должна
падать из-за недоступного мессенджера. О неудаче сообщаем возвратом
False — письмо остаётся запасным каналом.
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
    base_url = (getattr(settings, "VOX_API_URL", "") or "").rstrip("/")
    token = getattr(settings, "VOX_BOT_TOKEN", "")
    user_id = getattr(settings, "VOX_BOT_USER_ID", "")
    room_id = getattr(settings, "VOX_SUPPORT_ROOM_ID", "")

    if not (base_url and token and user_id and room_id):
        logger.warning("Vox не настроен — сообщение из кабинета юрлица не отправлено")
        return False

    header = ["*Обращение из кабинета юрлица: {}*".format(organization_name)]

    if author:
        header.append("Автор: {}".format(author))
    if contact:
        header.append("Обратная связь: {}".format(contact))

    payload = {
        "roomId": room_id,
        "text": "\n".join(header) + "\n\n" + text.strip(),
    }

    try:
        response = requests.post(
            "{}/api/v1/chat.postMessage".format(base_url),
            json=payload,
            headers={"X-Auth-Token": token, "X-User-Id": user_id},
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        result = response.json()
    except Exception:
        logger.warning("Не удалось отправить сообщение в Vox", exc_info=True)
        return False

    if not result.get("success"):
        logger.warning("Vox отклонил сообщение: %s", result.get("error"))
        return False

    return True
