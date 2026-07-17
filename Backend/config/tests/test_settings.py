import os
import logging
import runpy
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from config.settings.base import env_list
from config.logging import RequestIDFilter
from medical_audit.context import reset_current_request_id, set_current_request_id


PRODUCTION_ENV = {
    'DJANGO_SECRET_KEY': 'production-test-key-with-many-distinct-characters-1234567890!@#',
    'DJANGO_ALLOWED_HOSTS': 'api.example.com, app.example.com',
    'DJANGO_CSRF_TRUSTED_ORIGINS': 'https://api.example.com, https://app.example.com',
    'DJANGO_CORS_ALLOWED_ORIGINS': 'https://app.example.com',
    'FRONTEND_RESET_PASSWORD_URL': 'https://app.example.com/reset-password/confirm',
    'DATABASE_NAME': 'gahambani',
    'DATABASE_USER': 'gahambani_user',
    'DATABASE_PASSWORD': 'database-test-password',
    'DATABASE_HOST': 'db.example.com',
    'DATABASE_PORT': '5432',
    'DATABASE_SSLMODE': 'require',
    'DJANGO_EMAIL_BACKEND': 'django.core.mail.backends.smtp.EmailBackend',
    'DJANGO_EMAIL_HOST': 'smtp.example.com',
    'DJANGO_EMAIL_PORT': '587',
    'DJANGO_EMAIL_HOST_USER': 'smtp-user',
    'DJANGO_EMAIL_HOST_PASSWORD': 'smtp-test-password',
    'DJANGO_EMAIL_USE_TLS': 'true',
    'DJANGO_EMAIL_USE_SSL': 'false',
    'DJANGO_DEFAULT_FROM_EMAIL': 'GahamBani <no-reply@example.com>',
    'DJANGO_TRUST_X_FORWARDED_PROTO': 'true',
    'DRF_NUM_PROXIES': '1',
    'ALERT_THRESHOLDS_MEDICALLY_VALIDATED': 'true',
    'ALERT_BP_VERY_LOW_SYSTOLIC': '90',
    'ALERT_BP_VERY_LOW_DIASTOLIC': '60',
    'ALERT_BP_ELEVATED_SYSTOLIC': '140',
    'ALERT_BP_ELEVATED_DIASTOLIC': '90',
    'ALERT_BP_VERY_HIGH_SYSTOLIC': '180',
    'ALERT_BP_VERY_HIGH_DIASTOLIC': '120',
    'ALERT_BP_CRITICAL_SYSTOLIC': '180',
    'ALERT_BP_CRITICAL_DIASTOLIC': '120',
    'ALERT_HR_LOW': '40',
    'ALERT_HR_HIGH': '130',
    'ALERT_GLUCOSE_VERY_LOW_MG_DL': '54',
    'ALERT_GLUCOSE_HIGH_MG_DL': '180',
    'ALERT_GLUCOSE_VERY_HIGH_MG_DL': '250',
    'ALERT_HBA1C_HIGH_PERCENT': '8',
}


def load_production_settings(environment=None):
    values = PRODUCTION_ENV if environment is None else environment
    with patch.dict(os.environ, values, clear=True):
        return runpy.run_module(
            'config.settings.production',
            run_name='config.settings._production_test',
        )


def load_staging_settings(environment=None):
    values = PRODUCTION_ENV if environment is None else environment
    with patch.dict(os.environ, values, clear=True):
        return runpy.run_module(
            'config.settings.staging',
            run_name='config.settings._staging_test',
        )


class DefaultOnlyConfig:
    """Config source that exposes only defaults, simulating a missing .env."""

    def __call__(self, name, default=None, cast=None):
        return cast(default) if cast else default


class EnvironmentSettingsTests(SimpleTestCase):
    def test_production_requires_secret_key(self):
        environment = {**PRODUCTION_ENV}
        environment.pop('DJANGO_SECRET_KEY')

        with self.assertRaisesMessage(ImproperlyConfigured, 'DJANGO_SECRET_KEY'):
            load_production_settings(environment)

    def test_production_rejects_short_secret_key(self):
        environment = {**PRODUCTION_ENV, 'DJANGO_SECRET_KEY': 'too-short'}

        with self.assertRaisesMessage(ImproperlyConfigured, 'at least 50 characters'):
            load_production_settings(environment)

    def test_production_requires_complete_database_configuration(self):
        environment = {**PRODUCTION_ENV}
        environment.pop('DATABASE_NAME')

        with self.assertRaisesMessage(ImproperlyConfigured, 'DATABASE_NAME'):
            load_production_settings(environment)

    def test_production_requires_encrypted_database_connections(self):
        invalid = {**PRODUCTION_ENV, 'DATABASE_SSLMODE': 'disable'}

        with self.assertRaisesMessage(ImproperlyConfigured, 'DATABASE_SSLMODE'):
            load_production_settings(invalid)

    def test_production_security_and_parsed_origins(self):
        environment = {**PRODUCTION_ENV, 'DJANGO_DEBUG': 'true'}

        production = load_production_settings(environment)

        self.assertFalse(production['DEBUG'])
        self.assertEqual(
            production['ALLOWED_HOSTS'],
            ['api.example.com', 'app.example.com'],
        )
        self.assertEqual(
            production['CSRF_TRUSTED_ORIGINS'],
            ['https://api.example.com', 'https://app.example.com'],
        )
        self.assertEqual(
            production['CORS_ALLOWED_ORIGINS'],
            ['https://app.example.com'],
        )
        self.assertFalse(production['CORS_ALLOW_CREDENTIALS'])
        self.assertTrue(production['SESSION_COOKIE_SECURE'])
        self.assertTrue(production['CSRF_COOKIE_SECURE'])
        self.assertTrue(production['SECURE_SSL_REDIRECT'])
        self.assertGreater(production['SECURE_HSTS_SECONDS'], 0)
        self.assertEqual(
            production['SECURE_PROXY_SSL_HEADER'],
            ('HTTP_X_FORWARDED_PROTO', 'https'),
        )

    def test_production_rejects_in_memory_email_backend(self):
        environment = {
            **PRODUCTION_ENV,
            'DJANGO_EMAIL_BACKEND': 'django.core.mail.backends.locmem.EmailBackend',
        }

        with self.assertRaisesMessage(ImproperlyConfigured, 'EMAIL_BACKEND'):
            load_production_settings(environment)

    def test_production_requires_professionally_validated_alert_thresholds(self):
        environment = {**PRODUCTION_ENV, 'ALERT_THRESHOLDS_MEDICALLY_VALIDATED': 'false'}
        with self.assertRaisesMessage(ImproperlyConfigured, 'ALERT_THRESHOLDS_MEDICALLY_VALIDATED'):
            load_production_settings(environment)

    def test_env_list_strips_spaces_and_empty_values(self):
        with patch.dict(
            os.environ,
            {'HOSTS': 'api.example.com, app.example.com, ,'},
            clear=True,
        ):
            self.assertEqual(
                env_list('HOSTS'),
                ['api.example.com', 'app.example.com'],
            )

    def test_development_imports_without_production_secrets(self):
        with patch('decouple.AutoConfig', return_value=DefaultOnlyConfig()):
            development = runpy.run_module(
                'config.settings.development',
                run_name='config.settings._development_test',
            )

        self.assertTrue(development['DEBUG'])
        self.assertEqual(
            development['EMAIL_BACKEND'],
            'django.core.mail.backends.locmem.EmailBackend',
        )
        self.assertEqual(
            development['DATABASES']['default']['ENGINE'],
            'django.db.backends.sqlite3',
        )

    def test_test_settings_use_postgresql_when_ci_database_is_configured(self):
        environment = {
            'DATABASE_NAME': 'gahambani_ci',
            'DATABASE_USER': 'gahambani_ci',
            'DATABASE_PASSWORD': 'not-a-real-secret',
            'DATABASE_HOST': '127.0.0.1',
            'DATABASE_PORT': '5432',
        }
        with patch.dict(os.environ, environment, clear=True):
            test_settings = runpy.run_module(
                'config.settings.test',
                run_name='config.settings._test_database_test',
            )

        database = test_settings['DATABASES']['default']
        self.assertEqual(database['ENGINE'], 'django.db.backends.postgresql')
        self.assertEqual(database['NAME'], 'gahambani_ci')
        self.assertEqual(database['CONN_MAX_AGE'], 0)

    def test_staging_inherits_production_security_without_demo_data(self):
        staging = load_staging_settings()

        self.assertEqual(staging['ENVIRONMENT'], 'staging')
        self.assertFalse(staging['DEBUG'])
        self.assertFalse(staging['ALLOW_DEMO_DATA'])
        self.assertTrue(staging['SECURE_SSL_REDIRECT'])
        self.assertTrue(staging['SESSION_COOKIE_SECURE'])
        self.assertTrue(staging['CSRF_COOKIE_SECURE'])
        self.assertNotIn('*', staging['ALLOWED_HOSTS'])
        self.assertFalse(staging['CORS_ALLOW_CREDENTIALS'])
        self.assertFalse(staging['MEDICAL_DOCUMENT_STORAGE_DURABLE'])
        self.assertEqual(staging['LOGGING']['root']['level'], 'INFO')
        self.assertNotIn(PRODUCTION_ENV['DJANGO_SECRET_KEY'], str(staging['LOGGING']))
        self.assertNotIn(PRODUCTION_ENV['DATABASE_PASSWORD'], str(staging['LOGGING']))

    def test_request_id_logging_filter_adds_correlation_without_payload(self):
        token = set_current_request_id('5fa64293-9e86-4c7a-835c-7f18aa56e4b2')
        try:
            record = logging.LogRecord(
                name='test',
                level=logging.INFO,
                pathname=__file__,
                lineno=1,
                msg='safe message',
                args=(),
                exc_info=None,
            )
            self.assertTrue(RequestIDFilter().filter(record))
        finally:
            reset_current_request_id(token)

        self.assertEqual(
            record.request_id,
            '5fa64293-9e86-4c7a-835c-7f18aa56e4b2',
        )
        self.assertFalse(hasattr(record, 'request_body'))
