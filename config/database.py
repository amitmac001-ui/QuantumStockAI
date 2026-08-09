from __future__ import annotations

from pathlib import Path
from typing import Mapping
from urllib.parse import parse_qs, unquote, urlparse

from django.core.exceptions import ImproperlyConfigured


POSTGRES_SCHEMES = frozenset({"postgres", "postgresql"})
SUPPORTED_OPTIONS = frozenset({
    "sslmode",
    "channel_binding",
    "target_session_attrs",
    "connect_timeout",
})


def build_database_config(base_dir: Path, environ: Mapping[str, str]):
    """Use Neon/PostgreSQL only when DATABASE_URL is explicitly present."""

    database_url = str(environ.get("DATABASE_URL", "") or "").strip()
    if not database_url:
        return {
            "ENGINE": str(
                environ.get("DB_ENGINE", "django.db.backends.sqlite3")
            ),
            "NAME": environ.get("DB_NAME") or base_dir / "db.sqlite3",
            "USER": str(environ.get("DB_USER", "") or ""),
            "PASSWORD": str(environ.get("DB_PASSWORD", "") or ""),
            "HOST": str(environ.get("DB_HOST", "") or ""),
            "PORT": str(environ.get("DB_PORT", "") or ""),
            "CONN_MAX_AGE": 600,
            "CONN_HEALTH_CHECKS": True,
        }

    parsed = urlparse(database_url)
    if parsed.scheme.lower() not in POSTGRES_SCHEMES:
        raise ImproperlyConfigured("DATABASE_URL must use postgres/postgresql.")
    name = unquote(parsed.path.lstrip("/"))
    if not all((parsed.hostname, name, parsed.username)):
        raise ImproperlyConfigured("DATABASE_URL is incomplete.")
    query = parse_qs(parsed.query, keep_blank_values=False)
    options = {
        key: values[-1]
        for key, values in query.items()
        if key in SUPPORTED_OPTIONS and values
    }
    options.setdefault("sslmode", "require")
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": name,
        "USER": unquote(parsed.username),
        "PASSWORD": unquote(parsed.password or ""),
        "HOST": parsed.hostname,
        "PORT": str(parsed.port or 5432),
        "OPTIONS": options,
        # GitHub Actions is a short-lived worker; never retain idle connections.
        "CONN_MAX_AGE": 0,
        "CONN_HEALTH_CHECKS": True,
    }
