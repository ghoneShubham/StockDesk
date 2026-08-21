"""
Production settings — Day 13+14.

DEBUG is always False. Set AWS_STORAGE_BUCKET_NAME to serve media from S3
(product images + invoice PDFs). Static files are collected to STATIC_ROOT
and served by nginx. Email uses SES SMTP; ops alerts go through EmailOutbox.
"""

from decouple import Csv, config

from .base import *  # noqa: F401,F403
from .base import STORAGES as BASE_STORAGES

# --- Non-negotiable: DEBUG is False in production from the first deploy. ---
DEBUG = False

# Values come from .env — do NOT hardcode IPs/domains here.
ALLOWED_HOSTS = config("DJANGO_ALLOWED_HOSTS", cast=Csv())
CSRF_TRUSTED_ORIGINS = config("CSRF_TRUSTED_ORIGINS", default="", cast=Csv())

# --- Security hardening (behind nginx TLS) ---
SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", default=True, cast=bool)
# When testing on bare HTTP + public IP, set SECURE_SSL_REDIRECT=False in .env
# so login cookies are not marked Secure-only.
SESSION_COOKIE_SECURE = config("SESSION_COOKIE_SECURE", default=SECURE_SSL_REDIRECT, cast=bool)
CSRF_COOKIE_SECURE = config("CSRF_COOKIE_SECURE", default=SECURE_SSL_REDIRECT, cast=bool)
SECURE_HSTS_SECONDS = config("SECURE_HSTS_SECONDS", default=60 * 60 * 24 * 30, cast=int)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True

# Hashed static filenames for cache-busting; nginx serves STATIC_ROOT.
STORAGES = {
    **BASE_STORAGES,
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.ManifestStaticFilesStorage",
    },
}

# --- S3 media (Day 14). Empty bucket name → keep local FileSystemStorage (Day 13). ---
AWS_ACCESS_KEY_ID = config("AWS_ACCESS_KEY_ID", default="")
AWS_SECRET_ACCESS_KEY = config("AWS_SECRET_ACCESS_KEY", default="")
AWS_STORAGE_BUCKET_NAME = config("AWS_STORAGE_BUCKET_NAME", default="")
AWS_S3_REGION_NAME = config("AWS_S3_REGION_NAME", default="ap-south-1")
AWS_DEFAULT_ACL = None
AWS_S3_FILE_OVERWRITE = False
AWS_QUERYSTRING_AUTH = True
AWS_QUERYSTRING_EXPIRE = 3600

if AWS_STORAGE_BUCKET_NAME:
    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {"location": "media"},
    }

# --- Email via SES SMTP ---
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = config("EMAIL_HOST", default="email-smtp.ap-south-1.amazonaws.com")
EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)
EMAIL_USE_TLS = True
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")

# Nightly pg_dump → S3 (backup_database management command)
BACKUP_RETENTION_DAYS = config("BACKUP_RETENTION_DAYS", default=7, cast=int)
BACKUP_S3_PREFIX = config("BACKUP_S3_PREFIX", default="backups")

# Prefer WeasyPrint on Ubuntu when system libs are installed; xhtml2pdf still works.
INVOICE_PDF_ENGINE = config("INVOICE_PDF_ENGINE", default="xhtml2pdf")

SENTRY_DSN = config("SENTRY_DSN", default="")
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(dsn=SENTRY_DSN, integrations=[DjangoIntegration()], traces_sample_rate=0.1)
