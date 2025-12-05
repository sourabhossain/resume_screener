from .base import *

DEBUG = False
SECRET_KEY = 'test-key-insecure-but-fine-for-tests'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

# Disable rate limiting for tests to avoid interference, or keep it if we want to test it.
# For now, let's keep it but tests might need to handle it.
# Actually, better to test with it enabled but be aware of limits.

# Speed up tests
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.MD5PasswordHasher',
]
