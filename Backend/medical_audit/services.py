import json
import logging
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from django.db import transaction

from .context import request_audit_context
from .models import AuditResult, MedicalAuditEvent


logger = logging.getLogger('medical_audit')
FORBIDDEN_KEY_PARTS = (
    'password', 'token', 'authorization', 'cookie', 'secret', 'jwt',
    'binary', 'content', 'contenu', 'body', 'physical_path', 'file_path',
    'storage_path',
)
MAX_STRING_LENGTH = 512
MAX_JSON_BYTES = 16 * 1024
MAX_ITEMS = 50
MAX_DEPTH = 4


def _safe_key(key):
    normalized = str(key).casefold().replace('-', '_')
    return not any(part in normalized for part in FORBIDDEN_KEY_PARTS)


def _clean_value(value, depth=0):
    if depth >= MAX_DEPTH:
        return '[truncated]'
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime, UUID)):
        return str(value)
    if isinstance(value, Path):
        return value.name[:MAX_STRING_LENGTH]
    if isinstance(value, bytes):
        return '[binary excluded]'
    if isinstance(value, str):
        return value[:MAX_STRING_LENGTH]
    if isinstance(value, dict):
        cleaned = {}
        for key, item in list(value.items())[:MAX_ITEMS]:
            if _safe_key(key):
                cleaned[str(key)[:100]] = _clean_value(item, depth + 1)
        return cleaned
    if isinstance(value, (list, tuple, set)):
        return [_clean_value(item, depth + 1) for item in list(value)[:MAX_ITEMS]]
    return str(value)[:MAX_STRING_LENGTH]


def sanitize_audit_json(value):
    cleaned = _clean_value(value if isinstance(value, dict) else {})
    if len(json.dumps(cleaned, ensure_ascii=False, default=str).encode('utf-8')) > MAX_JSON_BYTES:
        return {'truncated': True}
    return cleaned


def record_medical_audit_event(
    *, action, domain, resource_type, actor=None, patient=None,
    resource_id=None, result=AuditResult.SUCCESS, request=None,
    metadata=None, changes=None,
):
    """Best-effort, structured append-only medical audit writer."""
    context = request_audit_context(request) if request is not None else {}
    actor = actor if getattr(actor, 'is_authenticated', False) else None
    try:
        with transaction.atomic():
            return MedicalAuditEvent.objects.create(
                actor=actor,
                actor_reference=getattr(actor, 'pk', None),
                actor_role=(getattr(actor, 'role', '') or '')[:20],
                patient=patient,
                patient_reference=getattr(patient, 'pk', None),
                action=action,
                result=result,
                domain=domain,
                resource_type=str(resource_type)[:100],
                resource_id=resource_id,
                metadata=sanitize_audit_json(metadata or {}),
                changes=sanitize_audit_json(changes or {}),
                **context,
            )
    except Exception as exc:
        logger.error(
            'Medical audit persistence failed for action=%s resource_type=%s error_type=%s',
            action,
            str(resource_type)[:100],
            type(exc).__name__,
        )
        return None
