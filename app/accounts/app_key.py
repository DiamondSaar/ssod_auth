"""
Подпись аппаратным ключом из нашего мобильного приложения (Dominex).

На Android браузеры работают с ключами только через сервисы Google. На
телефонах без них (Huawei) вход админа касанием YubiKey в браузере
невозможен — проверено 11.11.2026. Приложение Dominex говорит с ключом
по NFC/USB само (библиотека Yubico) и подписывает тот же вызов WebAuthn,
что и браузер. Ключи — те же, что в «Безопасности» (RP ID auth.ssod.pro),
перерегистрация не нужна. Отличие одно: источник подписи — не сайт, а
приложение, подписанное нашим ключом (android:apk-key-hash:…), и его мы
принимаем только здесь (settings.APP_KEY_ALLOWED_ORIGINS).

Два сценария (модель AppKeyFlow):
- login   — вход в приложение: ключ + PIN ключа, без логина и пароля.
            Если приложение просит продукт — в ответе SSO-билет с amr=hwk.
- confirm — вход в браузере на телефоне: после пароля страница ключа
            предлагает «Подтвердить через приложение», приложение
            показывает, чей вход и откуда, подпись — касанием ключа,
            страница в браузере сама проходит дальше.
"""

import hashlib
import json
import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from django_otp import login as otp_login
from django_otp_webauthn.helpers import WebAuthnHelper

from accounts import second_factor, sso_tickets
from accounts.models import AppKeyFlow, AuthEvent, Product

logger = logging.getLogger(__name__)

FLOW_LIFETIME = timedelta(minutes=3)
APP_SCHEME_CONFIRM_URL = "dominex://key-confirm"


class AppKeyHelper(WebAuthnHelper):
    """Та же проверка, что у входа в браузере, но источник подписи —
    наше приложение, а не страница auth.ssod.pro."""

    def get_allowed_origins(self):
        return list(settings.APP_KEY_ALLOWED_ORIGINS)


def _session_hash(request):
    if not request.session.session_key:
        request.session.save()
    return hashlib.sha256(request.session.session_key.encode()).hexdigest()


def _new_flow(purpose, **fields):
    # Попутно чистим старые запросы, чтобы таблица не копилась.
    AppKeyFlow.objects.filter(expires_at__lt=timezone.now() - timedelta(hours=1)).delete()
    return AppKeyFlow.objects.create(
        token=secrets.token_urlsafe(32),
        purpose=purpose,
        expires_at=timezone.now() + FLOW_LIFETIME,
        **fields,
    )


def _open_flow(token, purpose):
    flow = AppKeyFlow.objects.filter(token=token, purpose=purpose).select_related("user").first()
    if flow is None or flow.is_expired or flow.completed_at:
        return None
    return flow


def _json_body(request):
    try:
        return json.loads(request.body or b"{}")
    except ValueError:
        return None


def _verify(request, flow, credential):
    """Проверить подпись ключа. Возвращает ключ (WebAuthnCredential) или None."""
    helper = AppKeyHelper(request)
    try:
        device = helper.authenticate_complete(user=flow.user, state=flow.state, data=credential)
    except Exception:  # noqa: BLE001 — любой сбой проверки подписи = отказ
        logger.warning("app-key: подпись отклонена (%s)", flow.purpose, exc_info=True)
        return None
    if not device.confirmed or not device.user.is_active:
        return None
    return device


# ---------------------------------------------------------------------------
# Вход в приложение ключом
# ---------------------------------------------------------------------------


@csrf_exempt
@require_POST
def api_login_begin(request):
    """POST /api/v1/app-key/login/ {"product": "biographia"?} → вызов для ключа."""
    body = _json_body(request) or {}
    product = None
    if body.get("product"):
        product = Product.objects.filter(code=body["product"], is_active=True).first()
        if product is None:
            return JsonResponse({"error": "unknown_product"}, status=400)

    # Без логина: ключ сам скажет, чья это учётка, поэтому PIN обязателен.
    options, state = AppKeyHelper(request).authenticate_begin(user=None, require_user_verification=True)
    flow = _new_flow(AppKeyFlow.Purpose.LOGIN, product=product, state=state)
    return JsonResponse({"flow": flow.token, "options": options, "rp_id": options.get("rpId")})


# ---------------------------------------------------------------------------
# Подтверждение входа в браузере
# ---------------------------------------------------------------------------


@login_required
@require_POST
def browser_confirm_start(request):
    """POST /account/login/key/app/ — страница ключа просит приложение."""
    if not second_factor.requires_key(request.user):
        return JsonResponse({"error": "not_required"}, status=400)

    flow = _new_flow(
        AppKeyFlow.Purpose.CONFIRM,
        user=request.user,
        browser_session_hash=_session_hash(request),
        browser_ip=request.META.get("REMOTE_ADDR"),
        browser_agent=request.META.get("HTTP_USER_AGENT", "")[:500],
    )
    return JsonResponse({"flow": flow.token, "app_url": f"{APP_SCHEME_CONFIRM_URL}?flow={flow.token}"})


@login_required
@require_GET
def browser_confirm_status(request, token):
    """GET /account/login/key/app/<token>/ — браузер ждёт подписи."""
    flow = AppKeyFlow.objects.filter(token=token, purpose=AppKeyFlow.Purpose.CONFIRM).first()
    if flow is None or flow.user_id != request.user.pk or flow.browser_session_hash != _session_hash(request):
        return JsonResponse({"error": "not_found"}, status=404)

    if flow.completed_at and not flow.consumed_at and flow.device:
        flow.consumed_at = timezone.now()
        flow.save(update_fields=["consumed_at"])
        otp_login(request, flow.device)
        return JsonResponse({"confirmed": True})

    return JsonResponse({"confirmed": False, "expired": flow.is_expired})


@csrf_exempt
@require_GET
def api_confirm_options(request, token):
    """GET /api/v1/app-key/<token>/ — приложение: что подтверждаем + вызов для ключа."""
    flow = _open_flow(token, AppKeyFlow.Purpose.CONFIRM)
    if flow is None:
        return JsonResponse({"error": "expired_or_unknown"}, status=404)

    # Вход уже подтверждён паролем — от ключа нужно только касание.
    options, state = AppKeyHelper(request).authenticate_begin(user=flow.user, require_user_verification=False)
    flow.state = state
    flow.save(update_fields=["state"])
    return JsonResponse(
        {
            "flow": flow.token,
            "username": flow.user.username,
            "display_name": flow.user.get_full_name() or flow.user.username,
            "browser_ip": flow.browser_ip,
            "browser_agent": flow.browser_agent,
            "created_at": flow.created_at.isoformat(),
            "options": options,
            "rp_id": options.get("rpId"),
        }
    )


# ---------------------------------------------------------------------------
# Подпись ключом — общая для обоих сценариев
# ---------------------------------------------------------------------------


@csrf_exempt
@require_POST
def api_complete(request, token):
    """POST /api/v1/app-key/<token>/complete/ {"credential": {...}}."""
    flow = AppKeyFlow.objects.filter(token=token).select_related("user", "product").first()
    if flow is None or flow.is_expired or flow.completed_at or not flow.state:
        return JsonResponse({"error": "expired_or_unknown"}, status=404)

    body = _json_body(request)
    credential = (body or {}).get("credential")
    if not isinstance(credential, dict):
        return JsonResponse({"error": "credential_required"}, status=400)

    device = _verify(request, flow, credential)
    if device is None:
        AuthEvent.objects.create(
            user=flow.user,
            event_type=AuthEvent.EventType.KEY_LOGIN_FAILED,
            ip_address=request.META.get("REMOTE_ADDR"),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
            details={"app_key": flow.purpose},
        )
        return JsonResponse({"error": "key_rejected"}, status=400)

    flow.device = device
    flow.user = device.user
    flow.completed_at = timezone.now()
    flow.save(update_fields=["device", "user", "completed_at"])
    AuthEvent.objects.create(
        user=device.user,
        event_type=AuthEvent.EventType.KEY_LOGIN_SUCCESS,
        ip_address=request.META.get("REMOTE_ADDR"),
        user_agent=request.META.get("HTTP_USER_AGENT", ""),
        details={"app_key": flow.purpose, "key": device.name},
    )

    user = device.user
    response = {
        "ok": True,
        "purpose": flow.purpose,
        "username": user.username,
        "display_name": user.get_full_name() or user.username,
    }
    if flow.purpose == AppKeyFlow.Purpose.LOGIN and flow.product:
        if not sso_tickets.user_has_product(user, flow.product):
            return JsonResponse({"error": "no_product_access", **response}, status=403)
        response["ticket"] = sso_tickets.issue_ticket(
            user, flow.product, [second_factor.AMR_HARDWARE_KEY], request, via="app_key"
        )
    return JsonResponse(response)
