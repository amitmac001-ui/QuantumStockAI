import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from .market_service import MarketService
from ..providers.upstox_client import UpstoxClient

logger = logging.getLogger(__name__)


class QuoteSyncService:

    BATCH_SIZE = 200

    def __init__(self):
        self.client = UpstoxClient()
        self.market = MarketService()
        self.channel_layer = get_channel_layer()

    def _normalize_symbol(self, instrument, item):
        symbol = getattr(item, "symbol", None)

        if symbol:
            return symbol.upper().strip()

        if ":" in instrument:
            return instrument.split(":")[-1].upper().strip()

        if "|" in instrument:
            return instrument.split("|")[-1].upper().strip()

        return instrument.upper().strip()

    def _chunks(self, items, size):
        for i in range(0, len(items), size):
            yield items[i:i + size]

    def sync(self, instruments):

        if not instruments:
            return 0

        total_quotes = 0

        for batch in self._chunks(instruments, self.BATCH_SIZE):

            try:
                response = self.client.quote(",".join(batch))
            except Exception:
                logger.exception("Upstox quote request failed")
                continue

            data = getattr(response, "data", None)

            if not data:
                continue

            quotes = []

            for instrument, item in data.items():

                try:
                    symbol = self._normalize_symbol(instrument, item)

                    ohlc = getattr(item, "ohlc", None)

                    quote = {
                        "symbol": symbol,
                        "last_price": float(getattr(item, "last_price", 0) or 0),
                        "open_price": float(getattr(ohlc, "open", 0) or 0),
                        "high_price": float(getattr(ohlc, "high", 0) or 0),
                        "low_price": float(getattr(ohlc, "low", 0) or 0),
                        "previous_close": float(getattr(ohlc, "close", 0) or 0),
                        "volume": int(getattr(item, "volume", 0) or 0),
                    }

                    quotes.append(quote)

                    if self.channel_layer:
                        async_to_sync(
                            self.channel_layer.group_send
                        )(
                            "market",
                            {
                                "type": "market_message",
                                "data": quote,
                            },
                        )

                except Exception:
                    logger.exception(
                        "Quote processing failed: %s",
                        instrument,
                    )

            if quotes:
                self.market.bulk_save(quotes)
                total_quotes += len(quotes)

        return total_quotes
