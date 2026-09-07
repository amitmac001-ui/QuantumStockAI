import os

from django.core.exceptions import ImproperlyConfigured

from .base import *


def _csv(name: str) -> list[str]:
    return [value.strip() for value in os.getenv(name, "").split(",") if value.strip()]


DEBUG = False

# Production exports stay read-only unless a future deployment explicitly adds a
# separate, reviewed write path. Scanner-cache builds never publish to Sheets.
GOOGLE_SHEETS_ENABLED = False

if SECRET_KEY.startswith("django-insecure-"):
    raise ImproperlyConfigured(
        "Production requires a non-default DJANGO_SECRET_KEY environment variable."
    )
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured(
        "Production requires DJANGO_ALLOWED_HOSTS with the public hostname."
    )
if not os.getenv("DATABASE_URL", "").strip():
    raise ImproperlyConfigured("Production requires DATABASE_URL for PostgreSQL.")
if not os.getenv("REDIS_URL", "").strip():
    raise ImproperlyConfigured("Production requires REDIS_URL.")

CSRF_TRUSTED_ORIGINS = _csv("DJANGO_CSRF_TRUSTED_ORIGINS")
CORS_ALLOWED_ORIGINS = _csv("DJANGO_CORS_ALLOWED_ORIGINS")

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_SECURE_HSTS_SECONDS", "3600"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = os.getenv(
    "DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", "False"
).lower() == "true"
SECURE_HSTS_PRELOAD = os.getenv("DJANGO_SECURE_HSTS_PRELOAD", "False").lower() == "true"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": os.environ["REDIS_URL"],
        "KEY_PREFIX": "quantumstock",
        "TIMEOUT": 300,
    }
}
