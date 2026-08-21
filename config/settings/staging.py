"""
Staging settings — Day 14.

Same hardening as production, but intended for a separate DB + port on the
same EC2 host. Nothing should reach production until it has been exercised here.
"""

from decouple import Csv, config

from .prod import *  # noqa: F401,F403
from .prod import STORAGES as PROD_STORAGES

# Staging still never runs with DEBUG=True.
DEBUG = False

ALLOWED_HOSTS = config("DJANGO_ALLOWED_HOSTS", cast=Csv())
CSRF_TRUSTED_ORIGINS = config("CSRF_TRUSTED_ORIGINS", default="", cast=Csv())

# Staging often runs on HTTP + :8080 before a staging cert exists.
SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", default=False, cast=bool)
SESSION_COOKIE_SECURE = config("SESSION_COOKIE_SECURE", default=SECURE_SSL_REDIRECT, cast=bool)
CSRF_COOKIE_SECURE = config("CSRF_COOKIE_SECURE", default=SECURE_SSL_REDIRECT, cast=bool)
SECURE_HSTS_SECONDS = config("SECURE_HSTS_SECONDS", default=0, cast=int)

STORAGES = {**PROD_STORAGES}

# Keep staging uploads off production media/ when not using S3.
MEDIA_ROOT = BASE_DIR / "media_staging"

# Re-read S3 / email so a staging .env can point at a separate bucket if desired.
AWS_ACCESS_KEY_ID = config("AWS_ACCESS_KEY_ID", default="")
AWS_SECRET_ACCESS_KEY = config("AWS_SECRET_ACCESS_KEY", default="")
AWS_STORAGE_BUCKET_NAME = config("AWS_STORAGE_BUCKET_NAME", default="")
AWS_S3_REGION_NAME = config("AWS_S3_REGION_NAME", default="ap-south-1")

if AWS_STORAGE_BUCKET_NAME:
    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {"location": "media"},
    }
else:
    STORAGES["default"] = {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    }
