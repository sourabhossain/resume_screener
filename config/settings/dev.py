"""
Development settings for Resume Screening System.
"""
from .base import *

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-*l61k*h7!rg_es$$!moufn-t-u1t6a8g#=qm*-&o76wa=w1(nj'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ['*']

# Development-specific apps
INSTALLED_APPS += [
    # 'debug_toolbar',
]

# Development-specific middleware
# MIDDLEWARE += [
#     'debug_toolbar.middleware.DebugToolbarMiddleware',
# ]

# For Django Debug Toolbar
INTERNAL_IPS = ['127.0.0.1']

# Email backend for development
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
