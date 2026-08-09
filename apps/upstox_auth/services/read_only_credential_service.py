from __future__ import annotations

from django.conf import settings

from apps.upstox_auth.exceptions import TokenNotFoundError
from apps.upstox_auth.services.token_refresh_service import token_refresh_service


class ReadOnlyCredentialService:
    """Resolve credentials only for market/reference GET APIs."""

    @staticmethod
    def resolve() -> str:
        analytics_token = str(
            getattr(settings, "UPSTOX_ANALYTICS_TOKEN", "") or ""
        ).strip()
        if analytics_token:
            return analytics_token

        try:
            token = token_refresh_service.refresh_if_required()
        except TokenNotFoundError:
            value = str(getattr(settings, "UPSTOX_ACCESS_TOKEN", "") or "").strip()
        else:
            value = str(token.access_token or "").strip()
        if not value:
            raise RuntimeError("Upstox read-only credential is not configured.")
        return value


read_only_credential_service = ReadOnlyCredentialService()