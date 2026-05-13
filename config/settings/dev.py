"""
Development settings for Resume Screening System.
"""

import os

from .base import *

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = "django-insecure-*l61k*h7!rg_es$$!moufn-t-u1t6a8g#=qm*-&o76wa=w1(nj"

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ["*"]

# Django 4+ validates POST origins; without this, admin/login can return 403 on localhost/Docker.
CSRF_TRUSTED_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost",
    "http://127.0.0.1",
    "http://*.localhost",
]


INTERNAL_IPS = ["127.0.0.1"]

# Email backend for development
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Needed for cross-subdomain session sharing (e.g. ssl-wireless.localhost and demo.localhost)
SESSION_COOKIE_DOMAIN = '.localhost'

# Local development — use this org for all requests (override per .env)
FORCE_TENANT_SLUG = os.environ.get("FORCE_TENANT_SLUG", "demo")
