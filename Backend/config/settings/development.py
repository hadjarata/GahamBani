from copy import deepcopy

from decouple import AutoConfig, Csv
from alerts.config import DEVELOPMENT_ALERT_RULE_THRESHOLDS

from .base import *  # noqa: F403


config = AutoConfig(search_path=BASE_DIR)  # noqa: F405

# Explicitly local defaults. They must never be used for production.
SECRET_KEY = config(
    'DJANGO_SECRET_KEY',
    default='django-insecure-development-only-key-never-use-in-production-2026',
)
DEBUG = config('DJANGO_DEBUG', default=True, cast=bool)
ALLOW_DEMO_DATA = True
ALLOWED_HOSTS = config(
    'DJANGO_ALLOWED_HOSTS',
    default='localhost,127.0.0.1',
    cast=Csv(),
)

database_name = config('DATABASE_NAME', default='')
if database_name:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': database_name,
            'USER': config('DATABASE_USER', default=''),
            'PASSWORD': config('DATABASE_PASSWORD', default=''),
            'HOST': config('DATABASE_HOST', default='localhost'),
            'PORT': config('DATABASE_PORT', default='5432', cast=int),
        },
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',  # noqa: F405
        },
    }

CORS_ALLOWED_ORIGINS = config(
    'DJANGO_CORS_ALLOWED_ORIGINS',
    default='http://localhost:3000',
    cast=Csv(),
)
CSRF_TRUSTED_ORIGINS = config(
    'DJANGO_CSRF_TRUSTED_ORIGINS',
    default='http://localhost:3000',
    cast=Csv(),
)

EMAIL_BACKEND = config(
    'DJANGO_EMAIL_BACKEND',
    default='django.core.mail.backends.locmem.EmailBackend',
)
EMAIL_HOST = config('DJANGO_EMAIL_HOST', default='localhost')
EMAIL_PORT = config('DJANGO_EMAIL_PORT', default=25, cast=int)
EMAIL_HOST_USER = config('DJANGO_EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('DJANGO_EMAIL_HOST_PASSWORD', default='')
EMAIL_USE_TLS = config('DJANGO_EMAIL_USE_TLS', default=False, cast=bool)
EMAIL_USE_SSL = config('DJANGO_EMAIL_USE_SSL', default=False, cast=bool)
DEFAULT_FROM_EMAIL = config(
    'DJANGO_DEFAULT_FROM_EMAIL',
    default='GahamBani <no-reply@localhost>',
)
FRONTEND_RESET_PASSWORD_URL = config(
    'FRONTEND_RESET_PASSWORD_URL',
    default='http://localhost:3000/reset-password/confirm',
)

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': config('DJANGO_CACHE_LOCATION', default='gahambani-development'),
    },
}

REST_FRAMEWORK = deepcopy(REST_FRAMEWORK)  # noqa: F405
REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'].update({
    'anon': config('DRF_THROTTLE_RATE_ANON', default='100/day'),
    'user': config('DRF_THROTTLE_RATE_USER', default='1000/day'),
    'login': config('DRF_THROTTLE_RATE_LOGIN', default='5/minute'),
    'registration': config('DRF_THROTTLE_RATE_REGISTRATION', default='3/hour'),
    'password_reset': config('DRF_THROTTLE_RATE_PASSWORD_RESET', default='3/hour'),
    'password_reset_confirm': config(
        'DRF_THROTTLE_RATE_PASSWORD_RESET_CONFIRM',
        default='5/hour',
    ),
    'token_refresh': config('DRF_THROTTLE_RATE_TOKEN_REFRESH', default='20/hour'),
})
REST_FRAMEWORK['NUM_PROXIES'] = config('DRF_NUM_PROXIES', default=0, cast=int)
AUDIT_TRUSTED_PROXY_COUNT = REST_FRAMEWORK['NUM_PROXIES']
ALERT_THRESHOLDS_MEDICALLY_VALIDATED = False
ALERT_RULE_THRESHOLDS = deepcopy(DEVELOPMENT_ALERT_RULE_THRESHOLDS)

SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
