import os
from pathlib import Path

from .production import *  # noqa: F403


ENVIRONMENT = 'staging'
DEBUG = False
ALLOW_DEMO_DATA = False

# Staging remains HTTPS-only and keeps the explicit hosts/origins validated by
# production.py. Native Flutter clients do not require permissive browser CORS.

# Local container/VM storage is explicitly ephemeral. Configure a persistent
# mounted path for controlled staging tests; object storage remains future work.
MEDIA_ROOT = Path(
    os.environ.get('DJANGO_MEDIA_ROOT', BASE_DIR / 'staging-media')  # noqa: F405
)
MEDICAL_DOCUMENT_STORAGE_DURABLE = False

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'filters': {
        'request_id': {
            '()': 'config.logging.RequestIDFilter',
        },
    },
    'formatters': {
        'console': {
            'format': (
                'timestamp={asctime} level={levelname} logger={name} '
                'request_id={request_id} message="{message}"'
            ),
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'filters': ['request_id'],
            'formatter': 'console',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'medical_audit': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}
