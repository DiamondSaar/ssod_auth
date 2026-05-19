import hashlib
import json

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from accounts.models import SSODAccessKey


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
