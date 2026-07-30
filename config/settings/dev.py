from .base import *  # noqa: F401,F403
from .base import BASE_DIR, MIDDLEWARE, INSTALLED_APPS

DEBUG = True

INSTALLED_APPS += ["debug_toolbar"]

MIDDLEWARE = ["debug_toolbar.middleware.DebugToolbarMiddleware"] + MIDDLEWARE

INTERNAL_IPS = ["127.0.0.1"]

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Relaxed in dev only — production overrides these explicitly in prod.py.
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
