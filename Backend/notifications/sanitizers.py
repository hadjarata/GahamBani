import json
from datetime import date, datetime
from uuid import UUID


FORBIDDEN = (
    'password', 'token', 'authorization', 'cookie', 'secret', 'content',
    'contenu', 'body', 'path', 'reason', 'email', 'observed_value', 'exact_',
    'glucose', 'glycem', 'systol', 'diastol', 'blood_pressure', 'dosage',
)


def sanitize_metadata(value, *, public=False, depth=0):
    if depth > 3:
        return '[truncated]'
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, (date, datetime, UUID)):
        return str(value)
    if isinstance(value, bytes):
        return '[excluded]'
    if isinstance(value, str):
        return value[:255]
    if isinstance(value, (list, tuple)):
        return [sanitize_metadata(item, public=public, depth=depth + 1) for item in list(value)[:30]]
    if not isinstance(value, dict):
        return str(value)[:255]
    cleaned = {}
    for key, item in list(value.items())[:30]:
        normalized = str(key).casefold().replace('-', '_')
        if any(forbidden in normalized for forbidden in FORBIDDEN):
            continue
        cleaned[str(key)[:100]] = sanitize_metadata(item, public=public, depth=depth + 1)
    if len(json.dumps(cleaned, default=str).encode('utf-8')) > 8192:
        return {'truncated': True}
    return cleaned
