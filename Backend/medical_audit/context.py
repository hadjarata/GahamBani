import ipaddress
import uuid
from contextvars import ContextVar

from django.conf import settings


_current_request_id = ContextVar('gahambani_request_id', default=None)


def set_current_request_id(request_id):
    return _current_request_id.set(request_id)


def reset_current_request_id(token):
    _current_request_id.reset(token)


def get_current_request_id():
    return _current_request_id.get()


def _valid_ip(value):
    try:
        return str(ipaddress.ip_address(value))
    except (TypeError, ValueError):
        return None


def get_client_ip(request):
    remote_address = _valid_ip(request.META.get('REMOTE_ADDR'))
    trusted_proxy_count = max(int(getattr(settings, 'AUDIT_TRUSTED_PROXY_COUNT', 0)), 0)
    if not trusted_proxy_count:
        return remote_address
    forwarded = [item.strip() for item in request.META.get('HTTP_X_FORWARDED_FOR', '').split(',') if item.strip()]
    if len(forwarded) >= trusted_proxy_count:
        return _valid_ip(forwarded[-trusted_proxy_count]) or remote_address
    return remote_address


def clean_user_agent(value):
    return ''.join(char if char.isprintable() else ' ' for char in (value or '')).strip()[:512]


def request_audit_context(request):
    resolver_match = getattr(request, 'resolver_match', None)
    return {
        'http_method': request.method[:10],
        'endpoint': (getattr(resolver_match, 'view_name', '') or request.path)[:255],
        'ip_address': get_client_ip(request),
        'user_agent': clean_user_agent(request.META.get('HTTP_USER_AGENT')),
        'request_id': getattr(request, 'request_id', None),
    }


def valid_or_new_request_id(value):
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return uuid.uuid4()
