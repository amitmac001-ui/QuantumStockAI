from django.utils import timezone

from upstox_client import (
    ApiClient,
    Configuration,
    MarketQuoteApi,
)

from apps.upstox_auth.models import UpstoxToken

API_VERSION = "2.0"


class UpstoxClient:

    def __init__(self, user=None):
        self.user = user

        configuration = Configuration()
        configuration.access_token = self._get_access_token()

        self.client = ApiClient(configuration)
        self.quote_api = MarketQuoteApi(self.client)

    def _get_access_token(self):

        queryset = (
            UpstoxToken.objects
            .filter(is_active=True)
            .order_by("-created_at")
        )

        if self.user:
            queryset = queryset.filter(user=self.user)

        token = queryset.first()

        if token is None:
            raise RuntimeError("No active Upstox token found.")

        if token.is_expired:
            raise RuntimeError("Upstox access token expired.")

        return token.access_token

    def quote(self, symbols):
        return self.quote_api.get_full_market_quote(
            symbol=symbols,
            api_version=API_VERSION,
        )

    def ltp(self, symbols):
        return self.quote_api.ltp(
            symbol=symbols,
            api_version=API_VERSION,
        )

    def ohlc(self, symbols, interval="1d"):
        return self.quote_api.get_market_quote_ohlc(
            symbol=symbols,
            interval=interval,
            api_version=API_VERSION,
        )
