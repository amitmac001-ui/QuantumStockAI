"""
QuantumStock AI
Authentication Exception Definitions
"""

from __future__ import annotations


class UpstoxAuthException(Exception):
    """Base authentication exception."""


class OAuthStateValidationError(UpstoxAuthException):
    """OAuth state validation failed."""


class OAuthAuthorizationError(UpstoxAuthException):
    """Authorization failed."""


class OAuthTokenExchangeError(UpstoxAuthException):
    """Failed to exchange authorization code."""


class AccessTokenExpiredError(UpstoxAuthException):
    """Access token expired."""


class RefreshTokenExpiredError(UpstoxAuthException):
    """Refresh token expired."""


class RefreshTokenFailedError(UpstoxAuthException):
    """Unable to refresh access token."""


class TokenNotFoundError(UpstoxAuthException):
    """Active token not found."""


class TokenEncryptionError(UpstoxAuthException):
    """Token encryption/decryption failed."""


class RepositoryError(UpstoxAuthException):
    """Repository operation failed."""


class UpstoxAPIError(UpstoxAuthException):
    """Unexpected Upstox API error."""


class ConfigurationError(UpstoxAuthException):
    """Application configuration error."""
