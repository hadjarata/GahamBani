import os
from copy import deepcopy
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403
from .base import env_bool, env_int, env_list, env_required


def require_https_urls(name):
    urls = env_list(name, required=True)
    for url in urls:
        parsed = urlsplit(url)
        if parsed.scheme != 'https' or not parsed.netloc:
            raise ImproperlyConfigured(
                f'Every value in {name} must be an absolute HTTPS origin.'
            )
    return urls


def require_https_url(name):
    value = env_required(name)
    parsed = urlsplit(value)
    if parsed.scheme != 'https' or not parsed.netloc:
        raise ImproperlyConfigured(f'The {name} environment variable must use HTTPS.')
    return value


DEBUG = False

SECRET_KEY = env_required('DJANGO_SECRET_KEY')
if len(SECRET_KEY) < 50 or len(set(SECRET_KEY)) < 5:
    raise ImproperlyConfigured(
        'DJANGO_SECRET_KEY must contain at least 50 characters and sufficient entropy.'
    )

ALLOWED_HOSTS = env_list('DJANGO_ALLOWED_HOSTS', required=True)
if '*' in ALLOWED_HOSTS:
    raise ImproperlyConfigured('DJANGO_ALLOWED_HOSTS cannot contain a wildcard.')

CSRF_TRUSTED_ORIGINS = require_https_urls('DJANGO_CSRF_TRUSTED_ORIGINS')
CORS_ALLOWED_ORIGINS = require_https_urls('DJANGO_CORS_ALLOWED_ORIGINS')
CORS_ALLOW_CREDENTIALS = False
FRONTEND_RESET_PASSWORD_URL = require_https_url('FRONTEND_RESET_PASSWORD_URL')

DATABASE_SSLMODE = env_required('DATABASE_SSLMODE')
if DATABASE_SSLMODE not in {'require', 'verify-ca', 'verify-full'}:
    raise ImproperlyConfigured(
        'DATABASE_SSLMODE must be require, verify-ca, or verify-full.'
    )

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': env_required('DATABASE_NAME'),
        'USER': env_required('DATABASE_USER'),
        'PASSWORD': env_required('DATABASE_PASSWORD'),
        'HOST': env_required('DATABASE_HOST'),
        'PORT': env_int('DATABASE_PORT'),
        'CONN_MAX_AGE': env_int('DATABASE_CONN_MAX_AGE', default=60),
        'CONN_HEALTH_CHECKS': True,
        'OPTIONS': {
            'sslmode': DATABASE_SSLMODE,
        },
    },
}

EMAIL_BACKEND = env_required('DJANGO_EMAIL_BACKEND')
if EMAIL_BACKEND != 'django.core.mail.backends.smtp.EmailBackend':
    raise ImproperlyConfigured(
        'DJANGO_EMAIL_BACKEND must use Django\'s SMTP backend in production.'
    )
EMAIL_HOST = env_required('DJANGO_EMAIL_HOST')
EMAIL_PORT = env_int('DJANGO_EMAIL_PORT')
EMAIL_HOST_USER = env_required('DJANGO_EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = env_required('DJANGO_EMAIL_HOST_PASSWORD')
EMAIL_USE_TLS = env_bool('DJANGO_EMAIL_USE_TLS')
EMAIL_USE_SSL = env_bool('DJANGO_EMAIL_USE_SSL')
if EMAIL_USE_TLS and EMAIL_USE_SSL:
    raise ImproperlyConfigured('EMAIL_USE_TLS and EMAIL_USE_SSL cannot both be enabled.')
DEFAULT_FROM_EMAIL = env_required('DJANGO_DEFAULT_FROM_EMAIL')
EMAIL_TIMEOUT = env_int('DJANGO_EMAIL_TIMEOUT', default=10)

# LocMemCache is safe for a single process only. Configure a shared backend
# before running multiple production workers so throttle counters are shared.
CACHES = {
    'default': {
        'BACKEND': os.environ.get(
            'DJANGO_CACHE_BACKEND',
            'django.core.cache.backends.locmem.LocMemCache',
        ),
        'LOCATION': os.environ.get('DJANGO_CACHE_LOCATION', 'gahambani-production'),
    },
}

REST_FRAMEWORK = deepcopy(REST_FRAMEWORK)  # noqa: F405
REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'].update({
    'anon': os.environ.get('DRF_THROTTLE_RATE_ANON', '100/day'),
    'user': os.environ.get('DRF_THROTTLE_RATE_USER', '1000/day'),
    'login': os.environ.get('DRF_THROTTLE_RATE_LOGIN', '5/minute'),
    'registration': os.environ.get('DRF_THROTTLE_RATE_REGISTRATION', '3/hour'),
    'password_reset': os.environ.get('DRF_THROTTLE_RATE_PASSWORD_RESET', '3/hour'),
    'password_reset_confirm': os.environ.get(
        'DRF_THROTTLE_RATE_PASSWORD_RESET_CONFIRM',
        '5/hour',
    ),
    'token_refresh': os.environ.get('DRF_THROTTLE_RATE_TOKEN_REFRESH', '20/hour'),
})
REST_FRAMEWORK['NUM_PROXIES'] = env_int('DRF_NUM_PROXIES', default=0)
AUDIT_TRUSTED_PROXY_COUNT = REST_FRAMEWORK['NUM_PROXIES']

ALERT_THRESHOLDS_MEDICALLY_VALIDATED = env_bool('ALERT_THRESHOLDS_MEDICALLY_VALIDATED')
if not ALERT_THRESHOLDS_MEDICALLY_VALIDATED:
    raise ImproperlyConfigured(
        'ALERT_THRESHOLDS_MEDICALLY_VALIDATED must be true after professional review.',
    )
ALERT_RULE_THRESHOLDS = {
    'blood_pressure': {
        'very_low_systolic': env_int('ALERT_BP_VERY_LOW_SYSTOLIC'),
        'very_low_diastolic': env_int('ALERT_BP_VERY_LOW_DIASTOLIC'),
        'elevated_systolic': env_int('ALERT_BP_ELEVATED_SYSTOLIC'),
        'elevated_diastolic': env_int('ALERT_BP_ELEVATED_DIASTOLIC'),
        'very_high_systolic': env_int('ALERT_BP_VERY_HIGH_SYSTOLIC'),
        'very_high_diastolic': env_int('ALERT_BP_VERY_HIGH_DIASTOLIC'),
        'critical_systolic': env_int('ALERT_BP_CRITICAL_SYSTOLIC'),
        'critical_diastolic': env_int('ALERT_BP_CRITICAL_DIASTOLIC'),
    },
    'heart_rate': {
        'low': env_int('ALERT_HR_LOW'), 'high': env_int('ALERT_HR_HIGH'),
    },
    'blood_glucose': {
        'very_low_mg_dl': env_int('ALERT_GLUCOSE_VERY_LOW_MG_DL'),
        'high_mg_dl': env_int('ALERT_GLUCOSE_HIGH_MG_DL'),
        'very_high_mg_dl': env_int('ALERT_GLUCOSE_VERY_HIGH_MG_DL'),
        'hba1c_high_percent': env_int('ALERT_HBA1C_HIGH_PERCENT'),
    },
}

SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'

SECURE_HSTS_SECONDS = env_int('DJANGO_SECURE_HSTS_SECONDS', default=3600)
if SECURE_HSTS_SECONDS <= 0:
    raise ImproperlyConfigured('DJANGO_SECURE_HSTS_SECONDS must be greater than zero.')
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'
X_FRAME_OPTIONS = 'DENY'

# Enable only behind a controlled proxy that strips incoming forwarded headers.
if env_bool('DJANGO_TRUST_X_FORWARDED_PROTO'):
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
