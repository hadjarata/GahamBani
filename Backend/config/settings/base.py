import os
from datetime import timedelta
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured


BASE_DIR = Path(__file__).resolve().parent.parent.parent
_MISSING = object()


def env_required(name):
    value = os.environ.get(name)
    if value is None or not value.strip():
        raise ImproperlyConfigured(f'The {name} environment variable is required.')
    return value.strip()


def env_list(name, default=None, required=False):
    raw_value = os.environ.get(name)
    if raw_value is None:
        if required:
            raise ImproperlyConfigured(f'The {name} environment variable is required.')
        return list(default or [])

    values = [item.strip() for item in raw_value.split(',') if item.strip()]
    if required and not values:
        raise ImproperlyConfigured(f'The {name} environment variable cannot be empty.')
    return values


def env_bool(name, default=_MISSING):
    raw_value = os.environ.get(name)
    if raw_value is None:
        if default is _MISSING:
            raise ImproperlyConfigured(f'The {name} environment variable is required.')
        return default

    normalized = raw_value.strip().lower()
    if normalized in {'1', 'true', 'yes', 'on'}:
        return True
    if normalized in {'0', 'false', 'no', 'off'}:
        return False
    raise ImproperlyConfigured(
        f'The {name} environment variable must be a valid boolean value.'
    )


def env_int(name, default=_MISSING):
    raw_value = os.environ.get(name)
    if raw_value is None:
        if default is _MISSING:
            raise ImproperlyConfigured(f'The {name} environment variable is required.')
        return default
    try:
        return int(raw_value.strip())
    except ValueError as exc:
        raise ImproperlyConfigured(
            f'The {name} environment variable must be an integer.'
        ) from exc


INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'corsheaders',
    'rest_framework',
    'drf_spectacular',
    'rest_framework_simplejwt.token_blacklist',
    'accounts',
    'profiles',
    'medical_records',
    'monitoring',
    'alerts',
    'medical_audit',
    'notifications',
    'analytics',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'medical_audit.middleware.RequestIDMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'
MEDICAL_DOCUMENT_MAX_SIZE = 10 * 1024 * 1024
AUDIT_TRUSTED_PROXY_COUNT = 0
ANALYTICS_MAX_PERIOD_DAYS = env_int('ANALYTICS_MAX_PERIOD_DAYS', 365)
ANALYTICS_TREND_WINDOW_DAYS = env_int('ANALYTICS_TREND_WINDOW_DAYS', 7)
ANALYTICS_TREND_MIN_MEASUREMENTS = env_int('ANALYTICS_TREND_MIN_MEASUREMENTS', 2)
ANALYTICS_TREND_STABLE_THRESHOLD = os.environ.get('ANALYTICS_TREND_STABLE_THRESHOLD', '0.01')


# Medical documents must be served through an authenticated application view,
# never as a publicly accessible web-server directory.
FILE_UPLOAD_PERMISSIONS = 0o640
FILE_UPLOAD_DIRECTORY_PERMISSIONS = 0o750

AUTH_USER_MODEL = 'accounts.User'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

CORS_ALLOW_CREDENTIALS = False

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'accounts.authentication.VersionedJWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'EXCEPTION_HANDLER': 'api_contract.exception_handler.versioned_exception_handler',
    'DEFAULT_THROTTLE_CLASSES': (
        'accounts.throttles.ConfigurableAnonRateThrottle',
        'accounts.throttles.ConfigurableUserRateThrottle',
    ),
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/day',
        'user': '1000/day',
        'login': '5/minute',
        'registration': '3/hour',
        'password_reset': '3/hour',
        'password_reset_confirm': '5/hour',
        'token_refresh': '20/hour',
    },
    'NUM_PROXIES': 0,
}

ALLOW_DEMO_DATA = False

SPECTACULAR_SETTINGS = {
    'TITLE': 'GahamBani API',
    'DESCRIPTION': (
        'Documentation de l\'API GahamBani. Le Domaine 1 couvre '
        'l\'authentification et la gestion du compte utilisateur.'
    ),
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'COMPONENT_SPLIT_REQUEST': True,
    'ENUM_NAME_OVERRIDES': {
        'AssignmentStatusEnum': 'profiles.models.AssignmentStatus',
    },
    'POSTPROCESSING_HOOKS': [
        'drf_spectacular.hooks.postprocess_schema_enums',
        'api_contract.schema.attach_v1_error_schema',
    ],
    'PREPROCESSING_HOOKS': [
        'api_contract.schema.select_v1_when_aliases_are_present',
    ],
    'SWAGGER_UI_SETTINGS': {
        'persistAuthorization': True,
    },
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=15),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': False,
    'ALGORITHM': 'HS256',
    'AUTH_HEADER_TYPES': ('Bearer',),
}

SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SESSION_COOKIE_HTTPONLY = True
