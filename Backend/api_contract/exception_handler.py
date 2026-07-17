from rest_framework.exceptions import (
    AuthenticationFailed, MethodNotAllowed, NotAuthenticated, NotFound,
    PermissionDenied, Throttled, ValidationError,
)
from rest_framework.views import exception_handler

from . import codes


def _flatten_codes(value):
    if isinstance(value, dict):
        return [code for item in value.values() for code in _flatten_codes(item)]
    if isinstance(value, (list, tuple)):
        return [code for item in value for code in _flatten_codes(item)]
    return [str(value)]


def _field_errors(data):
    if not isinstance(data, dict):
        return {'non_field_errors': [str(item) for item in data]} if isinstance(data, list) else None
    errors = {}
    for field, value in data.items():
        if field in {'detail', 'code', 'messages'}:
            continue
        values = value if isinstance(value, list) else [value]
        errors[field] = [str(item) for item in values]
    return errors or None


def versioned_exception_handler(exc, context):
    """Keep legacy responses intact and expose a stable Flutter envelope on v1."""
    response = exception_handler(exc, context)
    if response is None:
        return None
    request = context.get('request')
    if request is None or not request.path.startswith('/api/v1/'):
        return response

    error_codes = _flatten_codes(exc.get_codes()) if hasattr(exc, 'get_codes') else []
    errors = None
    if isinstance(exc, ValidationError):
        code, detail = codes.VALIDATION_ERROR, 'Les données fournies sont invalides.'
        errors = _field_errors(response.data)
    elif isinstance(exc, (NotAuthenticated, AuthenticationFailed)):
        code = codes.INVALID_TOKEN if any(item in {'token_not_valid', 'authentication_failed'} for item in error_codes) else codes.AUTHENTICATION_REQUIRED
        detail = 'Authentification requise ou jeton invalide.'
    elif isinstance(exc, PermissionDenied):
        code, detail = codes.PERMISSION_DENIED, 'Vous n’avez pas l’autorisation d’effectuer cette action.'
    elif isinstance(exc, NotFound):
        code, detail = codes.NOT_FOUND, 'Ressource introuvable.'
    elif isinstance(exc, MethodNotAllowed):
        code, detail = codes.METHOD_NOT_ALLOWED, 'Méthode HTTP non autorisée.'
    elif isinstance(exc, Throttled):
        code, detail = codes.THROTTLED, 'Trop de requêtes.'
    else:
        code = getattr(exc, 'default_code', None) or (error_codes[0] if error_codes else 'api_error')
        detail = str(getattr(exc, 'detail', 'La requête a échoué.'))

    payload = {'code': code, 'detail': detail}
    if errors:
        payload['errors'] = errors
    if isinstance(exc, Throttled) and exc.wait is not None:
        payload['retry_after'] = int(exc.wait)
    response.data = payload
    return response
