from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from .market_service import MarketService
from ..providers.upstox_client import UpstoxClient


class QuoteSyncService:

    BATCH_SIZE = 200

    def __init__(self):
        self.client = UpstoxClient()
        self.market = MarketService()
        self.channel_layer = get_channel_layer()

    def _normalize_symbol(
        self,
        instrument,
        item,
    ):

        symbol = getattr(
            item,
            "symbol",
            None,
        )

        if symbol:
            return (
                symbol
                .upper()
                .strip()
            )

        if ":" in instrument:
            return (
                instrument
                .split(":")[-1]
                .upper()
                .strip()
            )

        if "|" in instrument:
            return (
                instrument
                .split("|")[-1]
                .upper()
                .strip()
            )

        return (
            instrument
            .upper()
            .strip()
        )

    def _chunks(
        self,
        items,
        size,
    ):

        for i in range(
            0,
            len(items),
            size,
        ):
            yield items[
                i:i + size
            ]

    def sync(
        self,
        instruments,
    ):

        if not instruments:
            return 0

        total_quotes = 0

        for batch in self._chunks(
            instruments,
            self.BATCH_SIZE,
        ):

            response = self.client.quote(
                ",".join(batch)
            )

            data = getattr(
                response,
                "data",
                None,
            )

            if not data:
                continue

            quotes = []

            for instrument, item in data.items():

                print("=" * 80)
                print("Instrument :", instrument)
                print("Upstox Symbol :", getattr(item, "symbol", None))
                print("=" * 80)

                symbol = self._normalize_symbol(
                    instrument,
                    item,
                )

                quote = {
                    "symbol": symbol,
                    "last_price": float(
                        item.last_price
                    ),
                    "open_price": float(
                        item.ohlc.open
                    ),
                    "high_price": float(
                        item.ohlc.high
                    ),
                    "low_price": float(
                        item.ohlc.low
                    ),
                    "previous_close": float(
                        item.ohlc.close
                    ),
                    "volume": int(
                        item.volume or 0
                    ),
                }

                quotes.append(
                    quote
                )

                async_to_sync(
                    self.channel_layer.group_send
                )(
                    "market",
                    {
                        "type": "market_message",
                        "data": quote,
                    },
                )

            self.market.bulk_save(
                quotes
            )

            total_quotes += len(
                quotes
            )

        return total_quotes
