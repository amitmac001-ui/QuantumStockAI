from __future__ import annotations

from django.db import transaction

from apps.upstox_auth.exceptions import (
    RepositoryError,
    TokenNotFoundError,
)
from apps.upstox_auth.models import UpstoxToken


class TokenRepository:

    @transaction.atomic
    def get(self) -> UpstoxToken:
        token = (
            UpstoxToken.objects
            .order_by("-updated_at", "-id")
            .first()
        )

        if token is None:
            raise TokenNotFoundError("Upstox token not found.")

        return token

    @transaction.atomic
    def save(
        self,
        *,
        access_token: str,
        refresh_token: str | None,
        expires_at,
    ) -> UpstoxToken:
        token = (
            UpstoxToken.objects
            .order_by("-updated_at", "-id")
            .first()
        )

        if token is None:
            token = UpstoxToken()

        token.access_token = access_token
        token.refresh_token = refresh_token
        token.expires_at = expires_at
        token.save()

        return token

    @transaction.atomic
    def delete(self) -> None:
        deleted, _ = UpstoxToken.objects.all().delete()

        if deleted == 0:
            raise RepositoryError("No token found to delete.")


token_repository = TokenRepository()
