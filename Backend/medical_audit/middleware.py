import logging

from .context import (
    reset_current_request_id,
    set_current_request_id,
    valid_or_new_request_id,
)


logger = logging.getLogger('django.request')


class RequestIDMiddleware:
    """Attach correlation only; never inspect or log request bodies."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.request_id = valid_or_new_request_id(
            request.headers.get('X-Request-ID'),
        )
        token = set_current_request_id(request.request_id)
        try:
            response = self.get_response(request)
            response['X-Request-ID'] = str(request.request_id)
            return response
        except Exception:
            # Deliberately omit exception text, headers and request body.
            logger.error('Unhandled request failure')
            raise
        finally:
            reset_current_request_id(token)
