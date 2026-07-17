ERROR_STATUSES = {'400', '401', '403', '404', '405', '409', '429', '500'}
LEGACY_MOBILE_PREFIXES = (
    '/api/auth/', '/api/profiles/', '/api/monitoring/', '/api/medical-records/',
    '/api/alerts/', '/api/notifications/', '/api/analytics/',
)


def select_v1_when_aliases_are_present(endpoints):
    """Make the default CLI schema represent v1 when both route generations exist."""
    has_v1 = any(path.startswith('/api/v1/') for path, *_ in endpoints)
    has_legacy = any(path.startswith(LEGACY_MOBILE_PREFIXES) for path, *_ in endpoints)
    if not (has_v1 and has_legacy):
        return endpoints
    return [
        endpoint for endpoint in endpoints
        if not endpoint[0].startswith(LEGACY_MOBILE_PREFIXES)
    ]


def attach_v1_error_schema(result, generator, request, public):
    """Describe the centralized v1 error envelope without changing legacy docs."""
    if not any(path.startswith('/api/v1/') for path in result.get('paths', {})):
        return result
    schemas = result.setdefault('components', {}).setdefault('schemas', {})
    schemas['V1Error'] = {
        'type': 'object',
        'required': ['code', 'detail'],
        'properties': {
            'code': {'type': 'string', 'example': 'validation_error'},
            'detail': {'type': 'string'},
            'errors': {
                'type': 'object', 'additionalProperties': {
                    'type': 'array', 'items': {'type': 'string'},
                },
            },
            'retry_after': {'type': 'integer', 'minimum': 0},
        },
    }
    for path, path_item in result.get('paths', {}).items():
        if not path.startswith('/api/v1/'):
            continue
        for operation in path_item.values():
            if not isinstance(operation, dict) or 'responses' not in operation:
                continue
            for status, response in operation['responses'].items():
                if status in ERROR_STATUSES:
                    response['content'] = {
                        'application/json': {'schema': {'$ref': '#/components/schemas/V1Error'}},
                    }
    return result
