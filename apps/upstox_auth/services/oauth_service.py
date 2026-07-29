from __future__ import annotations

import logging
import secrets

from django.db import transaction

from apps.upstox_auth.exceptions import OAuthStateValidationError
from apps.upstox_auth.repositories.token_repository import token_repository

logger = logging.getLogger(__name__)


class OAuthService:

    @staticmethod
    def generate_state() -> str:
        return secrets.token_urlsafe(32)

    @staticmethod
    def validate_state(session_state: str, callback_state: str) -> None:
        if (
            not session_state
            or not callback_state
            or session_state != callback_state
        ):
            raise OAuthStateValidationError(
                "Invalid OAuth state."
            )

    @transaction.atomic
    def save_tokens(
        self,
        *,
        access_token: str,
        refresh_token: str | None,
        expires_at,
    ):
        logger.info("Saving Upstox tokens.")

        return token_repository.save(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
        )

    def active_token(self):
        return token_repository.get()

    def revoke(self):
        token_repository.delete()


oauth_service = OAuthService()
