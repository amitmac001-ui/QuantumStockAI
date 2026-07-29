from upstox_client import (
    ApiClient,
    Configuration,
    MarketQuoteApi,
)

from apps.upstox_auth.services.token_refresh_service import (
    token_refresh_service,
)

API_VERSION = "2.0"


class UpstoxClient:

    def __init__(self, user=None):
        self.user = user
        self._configure()

    def _configure(self):
        token = token_refresh_service.refresh_if_required()

        configuration = Configuration()
        configuration.access_token = token.access_token

        self.client = ApiClient(configuration)
        self.quote_api = MarketQuoteApi(self.client)

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
