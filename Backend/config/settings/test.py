import os
from copy import deepcopy
from alerts.config import DEVELOPMENT_ALERT_RULE_THRESHOLDS

from .base import *  # noqa: F403


SECRET_KEY = 'django-test-only-secret-key-not-for-production-gahambani-2026'
DEBUG = False
ALLOWED_HOSTS = ['testserver', 'localhost', '127.0.0.1']

if os.environ.get('DATABASE_NAME'):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': env_required('DATABASE_NAME'),  # noqa: F405
            'USER': env_required('DATABASE_USER'),  # noqa: F405
            'PASSWORD': env_required('DATABASE_PASSWORD'),  # noqa: F405
            'HOST': env_required('DATABASE_HOST'),  # noqa: F405
            'PORT': env_int('DATABASE_PORT'),  # noqa: F405
            'CONN_MAX_AGE': 0,
        },
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': ':memory:',
        },
    }

PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.MD5PasswordHasher',
]

EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
DEFAULT_FROM_EMAIL = 'GahamBani Tests <test@example.com>'
FRONTEND_RESET_PASSWORD_URL = 'http://testserver/reset-password/confirm'

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'gahambani-tests',
    },
}

CORS_ALLOWED_ORIGINS = ['http://testserver']
CSRF_TRUSTED_ORIGINS = ['http://testserver']

REST_FRAMEWORK = deepcopy(REST_FRAMEWORK)  # noqa: F405
ALERT_THRESHOLDS_MEDICALLY_VALIDATED = False
ALERT_RULE_THRESHOLDS = deepcopy(DEVELOPMENT_ALERT_RULE_THRESHOLDS)
