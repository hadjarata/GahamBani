import logging

from medical_audit.context import get_current_request_id


class RequestIDFilter(logging.Filter):
    """Attach correlation metadata without inspecting request contents."""

    def filter(self, record):
        record.request_id = str(
            getattr(record, 'request_id', None)
            or get_current_request_id()
            or '-'
        )
        return True
