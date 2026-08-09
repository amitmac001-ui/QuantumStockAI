from __future__ import annotations

import time

from upstox_client import ApiClient, Configuration, MarketQuoteApi, MarketQuoteV3Api

from apps.upstox_auth.services.read_only_credential_service import (
    read_only_credential_service,
)

API_VERSION = "2.0"


class UpstoxClient:
    """Read-only market client; full quotes stay V2, OHLC/LTP use V3."""

    TOKEN_CHECK_INTERVAL_SECONDS = 60.0

    def __init__(self, user=None):
        self.user = user
        self._access_token = ""
        self._next_token_check_at = 0.0
        self.client: ApiClient | None = None
        self.quote_api: MarketQuoteApi | None = None
        self.quote_v3_api: MarketQuoteV3Api | None = None
        self._configure(force=True)

    def _resolve_access_token(self) -> str:
        return read_only_credential_service.resolve()

    def _configure(self, *, force: bool = False) -> None:
        access_token = self._resolve_access_token()
        if force or access_token != self._access_token:
            configuration = Configuration()
            configuration.access_token = access_token
            self.client = ApiClient(configuration)
            self.quote_api = MarketQuoteApi(self.client)
            self.quote_v3_api = MarketQuoteV3Api(self.client)
            self._access_token = access_token
        self._next_token_check_at = time.monotonic() + self.TOKEN_CHECK_INTERVAL_SECONDS

    def _ensure_configured(self) -> None:
        if time.monotonic() >= self._next_token_check_at:
            self._configure()
        if self.quote_api is None or self.quote_v3_api is None:
            raise RuntimeError("Upstox market quote client is unavailable.")

    def quote(self, symbols: str):
        self._ensure_configured()
        return self.quote_api.get_full_market_quote(symbol=symbols, api_version=API_VERSION)

    def ltp(self, symbols: str):
        self._ensure_configured()
        return self.quote_v3_api.get_ltp(instrument_key=symbols)

    def ohlc(self, symbols: str, interval: str = "1d"):
        self._ensure_configured()
        return self.quote_v3_api.get_market_quote_ohlc(
            interval=interval, instrument_key=symbols
        )