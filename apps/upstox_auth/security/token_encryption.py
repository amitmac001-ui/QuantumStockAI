from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

from apps.upstox_auth.exceptions import TokenEncryptionError


class TokenEncryption:

    def __init__(self) -> None:
        key = getattr(settings, "TOKEN_ENCRYPTION_KEY", None)

        if not key:
            raise TokenEncryptionError(
                "TOKEN_ENCRYPTION_KEY is not configured."
            )

        if isinstance(key, str):
            key = key.encode()

        self.cipher = Fernet(key)

    def encrypt(self, value: str) -> str:
        try:
            return self.cipher.encrypt(value.encode()).decode()
        except Exception as exc:
            raise TokenEncryptionError(str(exc)) from exc

    def decrypt(self, value: str) -> str:
        try:
            return self.cipher.decrypt(value.encode()).decode()
        except InvalidToken as exc:
            raise TokenEncryptionError("Invalid encrypted token.") from exc


token_encryption = TokenEncryption()
