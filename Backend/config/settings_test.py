"""Settings used by the automated test suite.

SQLite keeps tests isolated from the development PostgreSQL instance and does
not require the database role to have permission to create databases.
"""

from .settings import *  # noqa: F403


DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    },
}

PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.MD5PasswordHasher',
]
