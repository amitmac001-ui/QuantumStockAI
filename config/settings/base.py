from pathlib import Path
import os
from dotenv import load_dotenv

from config.database import build_database_config

BASE_DIR = Path(__file__).resolve().parent.parent.parent

load_dotenv(BASE_DIR / ".env")


SECRET_KEY = os.getenv(
    "DJANGO_SECRET_KEY",
    "django-insecure-temporary-secret-key-for-render"
)

if not SECRET_KEY:
    raise RuntimeError(
        "DJANGO_SECRET_KEY environment variable not found."
    )

DEBUG = os.getenv(
    "DJANGO_DEBUG",
    "False",
).lower() == "true"

ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv(
        "DJANGO_ALLOWED_HOSTS",
        "",
    ).split(",")
    if host.strip()
]

INSTALLED_APPS = [
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    "corsheaders",
    "django_filters",
    "drf_spectacular",

    "django_extensions",

    "channels",

    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",

    "apps.core",
    "apps.accounts",
    "apps.companies",
    "apps.market",
    "apps.scanner",
    "apps.dashboard",
    "apps.api",
    "apps.upstox_auth",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",

    "apps.core.middleware.request_id.RequestIDMiddleware",

    "whitenoise.middleware.WhiteNoiseMiddleware",

    "corsheaders.middleware.CorsMiddleware",

    "django.contrib.sessions.middleware.SessionMiddleware",

    "django.middleware.common.CommonMiddleware",

    "django.middleware.csrf.CsrfViewMiddleware",

    "django.contrib.auth.middleware.AuthenticationMiddleware",

    "django.contrib.messages.middleware.MessageMiddleware",

    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = (
    "config.outcome_worker_urls"
    if os.getenv("OUTCOME_WORKER_MODE", "0") == "1"
    else "config.urls"
)

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": build_database_config(BASE_DIR, os.environ),
}
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LANGUAGE_CODE = "en-us"

TIME_ZONE = "Asia/Kolkata"

USE_I18N = True

USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "accounts.User"

from datetime import timedelta

from datetime import timedelta

REST_FRAMEWORK = {

    "DEFAULT_AUTHENTICATION_CLASSES": (

        "rest_framework_simplejwt.authentication.JWTAuthentication",

    ),

    "EXCEPTION_HANDLER":
    "apps.core.exceptions.handler.custom_exception_handler",

    "DEFAULT_PERMISSION_CLASSES": (

        "rest_framework.permissions.IsAuthenticated",

    ),

    "DEFAULT_PAGINATION_CLASS":
    "apps.core.pagination.default.StandardPagination",

    "PAGE_SIZE": 25,

    "DEFAULT_RENDERER_CLASSES": (

        "rest_framework.renderers.JSONRenderer",

    ),

    "DEFAULT_PARSER_CLASSES": (

        "rest_framework.parsers.JSONParser",

    ),

    "DEFAULT_THROTTLE_CLASSES": (
    "apps.core.throttling.default.BurstAnonThrottle",
    "apps.core.throttling.default.BurstUserThrottle",

    ),

    "DEFAULT_THROTTLE_RATES": {
    "burst_anon": "100/min",
    "burst_user": "1000/min",

    },

    "DEFAULT_SCHEMA_CLASS":

        "drf_spectacular.openapi.AutoSchema",

    "DEFAULT_FILTER_BACKENDS": (

        "django_filters.rest_framework.DjangoFilterBackend",

    ),

    "DEFAULT_PAGINATION_CLASS":

        "rest_framework.pagination.PageNumberPagination",

    "PAGE_SIZE": 25,

    "DEFAULT_THROTTLE_CLASSES": (

        "rest_framework.throttling.AnonRateThrottle",

        "rest_framework.throttling.UserRateThrottle",

    ),

    "DEFAULT_THROTTLE_RATES": {

        "anon": "100/min",

        "user": "1000/min",

    },

}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(days=1),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=30),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

UPSTOX_CLIENT_ID = os.getenv("UPSTOX_CLIENT_ID")
UPSTOX_CLIENT_SECRET = os.getenv("UPSTOX_CLIENT_SECRET")
UPSTOX_REDIRECT_URI = os.getenv("UPSTOX_REDIRECT_URI")
UPSTOX_ACCESS_TOKEN = os.getenv("UPSTOX_ACCESS_TOKEN")
UPSTOX_ANALYTICS_TOKEN = os.getenv("UPSTOX_ANALYTICS_TOKEN", "")
CLOUD_COMPACT_MARKET_DATA = os.getenv(
    "CLOUD_COMPACT_MARKET_DATA", "0"
).strip().lower() in {"1", "true", "yes", "on"}

GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")
GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "")
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
GOOGLE_SHEETS_ENABLED = os.getenv("GOOGLE_SHEETS_ENABLED", "False").lower() == "true"
GOOGLE_SHEETS_SPREADSHEET_ID = os.getenv(
    "GOOGLE_SHEETS_SPREADSHEET_ID",
    GOOGLE_SHEET_ID or "1trS3KFYVXj4tUS7klxvVT1k51IuBQsKEEe6z6SXr4iI",
)
GOOGLE_SHEETS_TECHNICAL_TAB = os.getenv(
    "GOOGLE_SHEETS_TECHNICAL_TAB", "Technical Scanner"
)
TECHNICAL_SCANNER_PUBLISH_INTERVAL_SECONDS = int(
    os.getenv("TECHNICAL_SCANNER_PUBLISH_INTERVAL_SECONDS", "20")
)
TECHNICAL_SCANNER_STALE_AFTER_SECONDS = int(
    os.getenv("TECHNICAL_SCANNER_STALE_AFTER_SECONDS", "300")
)
SCAN_REPORT_CACHE_PATH = os.getenv("SCAN_REPORT_CACHE_PATH", "")

ASGI_APPLICATION = "config.asgi.application"

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [("127.0.0.1", 6379)],
        },
    },
}

STATICFILES_STORAGE = (
    "whitenoise.storage.CompressedManifestStaticFilesStorage"
)

CORS_ALLOW_ALL_ORIGINS = False

CORS_ALLOWED_ORIGINS = []

CORS_ALLOW_CREDENTIALS = True

CORS_ALLOW_HEADERS = [
    "*",
]


SPECTACULAR_SETTINGS = {

    "TITLE": "QuantumStock AI API",

    "DESCRIPTION":
    "Enterprise Stock Market API",

    "VERSION": "2.0.0",

}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "apps.core.logging.formatter.JSONFormatter",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "apps.core.logging.formatter.JSONFormatter",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
}
