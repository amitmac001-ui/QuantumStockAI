from __future__ import annotations

import logging

from apps.market.providers.upstox_client import UpstoxClient

logger = logging.getLogger(__name__)


class MarketDataService:

    def __init__(self, user=None):
        self.client = UpstoxClient(user=user)

    def ltp(self, symbols):
        try:
            return self.client.ltp(symbols)
        except Exception:
            return {
                "status": "error",
                "message": "Data Unavailable",
            }

    def quote(self, symbols):
        try:
            return self.client.quote(symbols)
        except Exception:
            return {
                "status": "error",
                "message": "Data Unavailable",
            }

    def ohlc(
        self,
        symbols,
        interval="1d",
    ):
        try:
            return self.client.ohlc(
                symbols,
                interval,
            )
        except Exception:
            return {
                "status": "error",
                "message": "Data Unavailable",
            }


market_data_service = MarketDataService()
