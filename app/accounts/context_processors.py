"""Окно чата с ССОД (виджет омниканала Dominex Vox) на страницах кабинета.

Тот же механизм, что в портале АТБ (backend/app/tickets/vox.py::chat_context):
гость виджета привязан к учётной записи постоянным токеном — подписью логина
секретом сайта. Человек с любого устройства попадает в тот же диалог, а в Vox
ССОД обращение видно с именем и логином, а не как «посетитель №…». Сам токен
ничего не открывает: это лишь имя гостя в омниканале.
Обращения приходят в отдел VOX_CHAT_DEPARTMENT («Сообщения из ССОД»).
"""

import hashlib
import hmac

from django.conf import settings


def vox_chat(request):
    url = getattr(settings, "VOX_CHAT_URL", "") or ""
    user = getattr(request, "user", None)
    if not url.startswith("https://") or user is None or not user.is_authenticated:
        return {}
    # В админке Django окно чата ни к чему — там работают сотрудники ССОД.
    if request.path.startswith("/admin"):
        return {}

    username = user.get_username()
    token = hmac.new(settings.SECRET_KEY.encode(), f"livechat:{username.lower()}".encode(),
                     hashlib.sha256).hexdigest()[:40]
    organization = getattr(user, "organization", None)
    person = user.get_full_name().strip()
    if getattr(user, "is_organization_account", False) and organization is not None:
        name = f"{organization.name} ({username})"
    elif person:
        name = f"{person}{' — ' + organization.name if organization else ''} ({username})"
    else:
        name = f"{organization.name} ({username})" if organization else username

    email = (user.email or "").strip()
    if not email:
        primary = user.emails.filter(is_primary=True).first() or user.emails.first()
        email = primary.email if primary else ""

    return {
        "vox_chat": {
            "url": url.rstrip("/"),
            "token": token,
            "name": name,
            "email": email,
            "department": getattr(settings, "VOX_CHAT_DEPARTMENT", "") or "",
        }
    }
