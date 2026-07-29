from __future__ import annotations

import logging

import requests
from django.conf import settings
from django.utils import timezone

from apps.upstox_auth.exceptions import RefreshTokenFailedError
from apps.upstox_auth.repositories.token_repository import token_repository

logger = logging.getLogger(__name__)


class TokenRefreshService:

    TOKEN_URL = "https://api.upstox.com/v2/login/authorization/token"

    def refresh_if_required(self):
        token = token_repository.get()

        if not token.needs_refresh:
            return token

        if not token.refresh_token:
            raise RefreshTokenFailedError(
                "Refresh token unavailable."
            )

        response = requests.post(
            self.TOKEN_URL,
            headers={
                "accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "refresh_token",
                "refresh_token": token.refresh_token,
                "client_id": settings.UPSTOX_CLIENT_ID,
                "client_secret": settings.UPSTOX_CLIENT_SECRET,
            },
            timeout=30,
        )

        data = response.json()

        if "access_token" not in data:
            raise RefreshTokenFailedError(str(data))

        expires_in = int(data.get("expires_in", 0))

        expires_at = (
            timezone.now() + timezone.timedelta(seconds=expires_in)
            if expires_in
            else None
        )

        return token_repository.save(
            access_token=data["access_token"],
            refresh_token=data.get(
                "refresh_token",
                token.refresh_token,
            ),
            expires_at=expires_at,
        )


token_refresh_service = TokenRefreshService()
