import hashlib
import hmac
import json

from django.conf import settings
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from accounts.models import AuthEvent, CustomUser, PersonalKeyMaterial, Product, SSODAccessKey, WebAuthnCredential


@csrf_exempt
@require_POST
def verify_access_key(request):
    """
    Проверка ключа доступа ССОД.

    Клиент передает ключ:
    - либо в JSON: {"key": "..."}
    - либо в заголовке: X-SSOD-Key: ...

    В базе сам ключ не хранится.
    Мы считаем SHA256 и ищем fingerprint.
    """

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        payload = {}

    raw_key = payload.get("key") or request.headers.get("X-SSOD-Key")

    if not raw_key:
        return JsonResponse(
            {
                "valid": False,
                "error": "key_required",
            },
            status=400,
        )

    fingerprint = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    try:
        access_key = SSODAccessKey.objects.select_related(
            "user",
            "user__organization",
            "user__position",
        ).get(
            fingerprint_sha256=fingerprint,
        )
    except SSODAccessKey.DoesNotExist:
        return JsonResponse(
            {
                "valid": False,
                "error": "invalid_key",
            },
            status=401,
        )

    user = access_key.user

    if access_key.status != SSODAccessKey.Status.ACTIVE:
        return JsonResponse(
            {
                "valid": False,
                "error": "key_not_active",
                "key_status": access_key.status,
            },
            status=403,
        )

    if access_key.expires_at and access_key.expires_at <= timezone.now():
        access_key.status = SSODAccessKey.Status.EXPIRED
        access_key.save(update_fields=["status", "updated_at"])

        return JsonResponse(
            {
                "valid": False,
                "error": "key_expired",
            },
            status=403,
        )

    if not user.is_active:
        return JsonResponse(
            {
                "valid": False,
                "error": "user_blocked",
            },
            status=403,
        )

    access_key.last_used_at = timezone.now()
    access_key.save(update_fields=["last_used_at", "updated_at"])

    return JsonResponse(
        {
            "valid": True,
            "user": {
                "id": str(user.uuid),
                "username": user.username,
                "full_name": user.full_name_ru,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "middle_name": user.middle_name,
                "email": user.email,
                "access_class": user.access_class,
                "is_active": user.is_active,
                "organization": {
                    "id": str(user.organization.uuid) if user.organization else None,
                    "name": user.organization.name if user.organization else None,
                },
                "position": {
                    "id": str(user.position.uuid) if user.position else None,
                    "name": user.position.name if user.position else None,
                },
            },
            "key": {
                "uuid": str(access_key.uuid),
                "name": access_key.name,
                "status": access_key.status,
                "issued_at": access_key.issued_at.isoformat(),
                "last_used_at": access_key.last_used_at.isoformat(),
            },
            "permissions": [],
        }
    )


ADMIN_UPDATE_ALLOWED_FIELDS = ("name", "product_url", "is_active", "sso_enabled")


@csrf_exempt
@require_POST
def admin_update_product(request):
    """
    Write-through admin bridge: Dominex's "Настройки -> Продукты и
    подключаемые модули" screen calls this to keep ssod_auth's own Product
    row (name/product_url/is_active/sso_enabled) in sync, instead of
    requiring a second manual edit here. The one call in the ecosystem
    that goes Dominex -> ssod_auth rather than the usual other way round -
    see biographia TZ section 13. Own secret (DOMINEX_ADMIN_API_KEY), own
    narrow field whitelist - not a general model CRUD endpoint.
    """

    provided = request.headers.get("X-Dominex-Admin-Key", "")
    expected = settings.DOMINEX_ADMIN_API_KEY

    if not expected or not hmac.compare_digest(provided, expected):
        return JsonResponse({"error": "unauthorized"}, status=401)

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid_json"}, status=400)

    code = (payload.get("code") or "").strip()
    if not code:
        return JsonResponse({"error": "code_required"}, status=400)

    updates = {field: payload[field] for field in ADMIN_UPDATE_ALLOWED_FIELDS if field in payload}

    product, created = Product.objects.get_or_create(
        code=code,
        defaults={"name": updates.get("name") or code, **updates},
    )

    changed = {}
    if not created:
        for field, value in updates.items():
            old_value = getattr(product, field)
            if old_value != value:
                changed[field] = {"old": old_value, "new": value}
                setattr(product, field, value)
        if changed:
            product.save(update_fields=list(changed.keys()) + ["updated_at"])

    AuthEvent.objects.create(
        user=None,
        event_type=AuthEvent.EventType.PRODUCT_CONFIG_SYNCED,
        details={"product_code": code, "created": created, "changed": changed},
    )

    return JsonResponse(
        {
            "ok": True,
            "code": product.code,
            "created": created,
            "changed": list(changed.keys()),
        }
    )


def _require_biographia_key(request):
    provided = request.headers.get("X-Biographia-Key-Api-Key", "")
    expected = settings.BIOGRAPHIA_KEY_API_KEY
    return bool(expected) and hmac.compare_digest(provided, expected)


PERSONAL_KEY_FIELDS = (
    "wrapped_master_key",
    "nonce",
    "kdf_algorithm",
    "kdf_salt",
    "kdf_memory_kib",
    "kdf_iterations",
    "kdf_parallelism",
)


def _material_payload(material):
    data = {field: getattr(material, field) for field in PERSONAL_KEY_FIELDS}
    data["provider"] = material.provider
    data["label"] = material.label
    data["credential_id"] = material.webauthn_credential.credential_id if material.webauthn_credential_id else None
    return data


@csrf_exempt
@require_POST
def store_personal_key_material(request):
    """
    Реестр личного ключа (biographia TZ раздел 4): принимает и хранит
    только зашифрованную (client-side wrapped) копию мастер-ключа
    Biographia плюс публичные параметры. Никогда не видит пароль,
    seed-фразу, PRF-секрет или расшифрованный ключ - это гарантирует
    сам протокол (шифрование происходит в браузере до этого запроса),
    не проверка здесь.

    `provider` выбирает, какая запись перезаписывается:
    - "password" (по умолчанию) - одна запись на пользователя, как и
      раньше (recovery-поток: новый пароль -> новая обёртка того же
      мастер-ключа).
    - "webauthn_prf" - требует `credential_id` (уже зарегистрированного
      через /webauthn-credentials/), одна запись на *credential*, не на
      пользователя - несколько токенов сосуществуют независимо.
    """

    if not _require_biographia_key(request):
        return JsonResponse({"error": "unauthorized"}, status=401)

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid_json"}, status=400)

    username = (payload.get("username") or "").strip()
    if not username:
        return JsonResponse({"error": "username_required"}, status=400)

    provider = payload.get("provider") or PersonalKeyMaterial.PROVIDER_PASSWORD
    if provider not in dict(PersonalKeyMaterial.PROVIDER_CHOICES):
        return JsonResponse({"error": "invalid_provider"}, status=400)

    missing = [f for f in PERSONAL_KEY_FIELDS if f not in payload]
    if missing:
        return JsonResponse({"error": "missing_fields", "fields": missing}, status=400)

    try:
        user = CustomUser.objects.get(username=username)
    except CustomUser.DoesNotExist:
        return JsonResponse({"error": "unknown_user"}, status=404)

    values = {field: payload[field] for field in PERSONAL_KEY_FIELDS}
    values["label"] = payload.get("label") or ""

    if provider == PersonalKeyMaterial.PROVIDER_WEBAUTHN_PRF:
        credential_id = (payload.get("credential_id") or "").strip()
        if not credential_id:
            return JsonResponse({"error": "credential_id_required_for_webauthn_prf"}, status=400)
        try:
            credential = WebAuthnCredential.objects.get(user=user, credential_id=credential_id)
        except WebAuthnCredential.DoesNotExist:
            return JsonResponse({"error": "unknown_credential"}, status=404)
        values["webauthn_credential"] = credential
        material, created = PersonalKeyMaterial.objects.update_or_create(
            user=user, provider=provider, webauthn_credential=credential, defaults=values
        )
    else:
        material, created = PersonalKeyMaterial.objects.update_or_create(
            user=user, provider=provider, webauthn_credential=None, defaults=values
        )

    AuthEvent.objects.create(
        user=user,
        event_type=AuthEvent.EventType.PERSONAL_KEY_MATERIAL_UPDATED,
        details={"action": "created" if created else "replaced", "provider": provider},
    )

    return JsonResponse({"ok": True, "created": created})


@csrf_exempt
def fetch_personal_key_material(request, username):
    """Read side of the registry above - same guard, returns every
    registered wrapped copy (password + any WebAuthn tokens) for the
    browser to try/unwrap locally. Empty list (not 404) when nothing is
    set up yet - unlike the single-record version this replaced, "no
    materials" is a valid, distinguishable list state on its own."""

    if not _require_biographia_key(request):
        return JsonResponse({"error": "unauthorized"}, status=401)

    materials = PersonalKeyMaterial.objects.filter(user__username=username).select_related("webauthn_credential")
    return JsonResponse({"materials": [_material_payload(m) for m in materials]})


def _credential_payload(credential):
    return {
        "credential_id": credential.credential_id,
        "public_key": credential.public_key,
        "sign_count": credential.sign_count,
        "transports": credential.transports,
        "label": credential.label,
        "last_used_at": credential.last_used_at.isoformat() if credential.last_used_at else None,
    }


@csrf_exempt
@require_POST
def store_webauthn_credential(request):
    """Registers a new WebAuthn credential for PRF-based personal-zone
    unlock (TZ section 4) - called once, right after Biographia's backend
    verifies a real `navigator.credentials.create()` attestation. Public
    key + sign_count only, same "server never sees the actual secret"
    rule as the key material endpoints above - the PRF secret itself
    never leaves the authenticator/platform."""

    if not _require_biographia_key(request):
        return JsonResponse({"error": "unauthorized"}, status=401)

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid_json"}, status=400)

    username = (payload.get("username") or "").strip()
    credential_id = (payload.get("credential_id") or "").strip()
    public_key = payload.get("public_key") or ""
    if not username or not credential_id or not public_key:
        return JsonResponse({"error": "username_credential_id_and_public_key_required"}, status=400)

    try:
        user = CustomUser.objects.get(username=username)
    except CustomUser.DoesNotExist:
        return JsonResponse({"error": "unknown_user"}, status=404)

    credential, created = WebAuthnCredential.objects.update_or_create(
        credential_id=credential_id,
        defaults={
            "user": user,
            "public_key": public_key,
            "sign_count": payload.get("sign_count") or 0,
            "transports": payload.get("transports") or [],
            "label": payload.get("label") or "",
        },
    )

    AuthEvent.objects.create(
        user=user,
        event_type=AuthEvent.EventType.PERSONAL_KEY_MATERIAL_UPDATED,
        details={"action": "webauthn_credential_created" if created else "webauthn_credential_replaced"},
    )

    return JsonResponse({"ok": True, "created": created})


@csrf_exempt
def fetch_webauthn_credentials(request, username):
    """List side - Biographia's backend calls this to build
    `allowCredentials` for an authentication ceremony (needs to know
    which credential_ids are valid for this user before it can even ask
    the browser to produce an assertion)."""

    if not _require_biographia_key(request):
        return JsonResponse({"error": "unauthorized"}, status=401)

    credentials = WebAuthnCredential.objects.filter(user__username=username)
    return JsonResponse({"credentials": [_credential_payload(c) for c in credentials]})


@csrf_exempt
@require_POST
def update_webauthn_sign_count(request, credential_id):
    """Clone-detection bookkeeping (WebAuthn spec): after each successful
    assertion, the authenticator's sign counter must have strictly
    increased - Biographia's backend verifies that itself and only calls
    this to persist the new value, this endpoint doesn't re-derive trust
    on its own."""

    if not _require_biographia_key(request):
        return JsonResponse({"error": "unauthorized"}, status=401)

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid_json"}, status=400)

    try:
        credential = WebAuthnCredential.objects.get(credential_id=credential_id)
    except WebAuthnCredential.DoesNotExist:
        return JsonResponse({"error": "unknown_credential"}, status=404)

    credential.sign_count = payload.get("sign_count", credential.sign_count)
    credential.last_used_at = timezone.now()
    credential.save(update_fields=["sign_count", "last_used_at", "updated_at"])

    return JsonResponse({"ok": True})
