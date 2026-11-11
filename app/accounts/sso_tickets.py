"""Короткоживущий подписанный SSO-билет для перехода в продукт экосистемы
(см. dominex/docs/module-interactions.md). Один источник для браузерного
перехода (views.sso_authorize) и входа ключом из приложения (app_key)."""

import uuid

import jwt
from django.conf import settings
from django.utils import timezone

from accounts.models import AuthEvent, UserProductAccess

SSO_TICKET_LIFETIME_SECONDS = 60


def user_has_product(user, product):
    return UserProductAccess.objects.filter(
        user=user,
        product=product,
        status=UserProductAccess.Status.ACTIVE,
    ).exists()


def issue_ticket(user, product, amr, request, **details):
    """amr — чем подтверждён вход: ["pwd"] или ["hwk"] (second_factor)."""
    now = timezone.now()
    jti = str(uuid.uuid4())
    payload = {
        "sub": user.username,
        "aud": product.code,
        "iat": int(now.timestamp()),
        "exp": int(now.timestamp()) + SSO_TICKET_LIFETIME_SECONDS,
        "jti": jti,
        # Продукт сам решает, пускать ли админа без ключа.
        "amr": amr,
    }
    ticket = jwt.encode(payload, settings.SSO_TICKET_SECRET, algorithm="HS256")

    AuthEvent.objects.create(
        user=user,
        event_type=AuthEvent.EventType.ACCESS_GRANTED,
        ip_address=request.META.get("REMOTE_ADDR"),
        user_agent=request.META.get("HTTP_USER_AGENT", ""),
        details={"sso_ticket_issued": True, "product": product.code, "jti": jti, "exp": payload["exp"], **details},
    )
    return ticket
