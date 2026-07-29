from __future__ import annotations

import base64
import hashlib
import hmac

from django.conf import settings

from apps.upstox_auth.exceptions import TokenEncryptionError


class TokenSecurity:
    def __init__(self) -> None:
        self._key = settings.SECRET_KEY.encode()

    def sign(self, token: str) -> str:
        sig = hmac.new(
            self._key,
            token.encode(),
            hashlib.sha256,
        ).digest()
        return base64.urlsafe_b64encode(sig).decode()

    def verify(self, token: str, signature: str) -> bool:
        expected = self.sign(token)
        return hmac.compare_digest(expected, signature)


token_security = TokenSecurity()
