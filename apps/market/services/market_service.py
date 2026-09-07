from decimal import Decimal

from django.db import transaction

from apps.market.models import (
    Exchange,
    MarketQuote,
    MarketStatus,
)


class MarketService:

    @staticmethod
    @transaction.atomic
    def save_quote(data):

        symbol = data["symbol"].upper()

        defaults = {
            "company": data.get("company"),
            "instrument_key": str(data.get("instrument_key", "") or ""),
            "company_name": data.get(
                "company_name",
                symbol,
            ),
            "last_price": Decimal(
                str(data.get("last_price", 0))
            ),
            "open_price": Decimal(
                str(data.get("open_price", 0))
            ),
            "high_price": Decimal(
                str(data.get("high_price", 0))
            ),
            "low_price": Decimal(
                str(data.get("low_price", 0))
            ),
            "previous_close": Decimal(
                str(data.get("previous_close", 0))
            ),
            "change": Decimal(
                str(data.get("change", 0))
            ),
            "change_percent": Decimal(
                str(data.get("change_percent", 0))
            ),
            "volume": int(
                data.get("volume", 0)
            ),
            "traded_value": Decimal(
                str(data.get("traded_value", 0))
            ),
            "market_status": data.get(
                "market_status",
                MarketStatus.CLOSED,
            ),
            "provider_state": str(
                data.get("provider_state", "DATA_UNAVAILABLE")
            ),
            "last_trade_time": data.get(
                "last_trade_time",
            ),
            "provider_timestamp": data.get(
                "provider_timestamp",
            ),
        }

        obj, _ = MarketQuote.objects.update_or_create(
            symbol=symbol,
            exchange=data.get(
                "exchange",
                Exchange.NSE,
            ),
            defaults=defaults,
        )

        return obj

    @staticmethod
    @transaction.atomic
    def bulk_save(quotes):

        if not quotes:
            return 0

        objects = []

        for item in quotes:

            objects.append(
                MarketQuote(
                    symbol=item["symbol"].upper(),
                    company=item.get("company"),
                    instrument_key=str(item.get("instrument_key", "") or ""),
                    exchange=item.get(
                        "exchange",
                        Exchange.NSE,
                    ),
                    company_name=item.get(
                        "company_name",
                        item["symbol"],
                    ),
                    last_price=Decimal(
                        str(item.get("last_price", 0))
                    ),
                    open_price=Decimal(
                        str(item.get("open_price", 0))
                    ),
                    high_price=Decimal(
                        str(item.get("high_price", 0))
                    ),
                    low_price=Decimal(
                        str(item.get("low_price", 0))
                    ),
                    previous_close=Decimal(
                        str(item.get("previous_close", 0))
                    ),
                    change=Decimal(
                        str(item.get("change", 0))
                    ),
                    change_percent=Decimal(
                        str(item.get("change_percent", 0))
                    ),
                    volume=int(
                        item.get("volume", 0)
                    ),
                    traded_value=Decimal(
                        str(item.get("traded_value", 0))
                    ),
                    market_status=item.get(
                        "market_status",
                        MarketStatus.CLOSED,
                    ),
                    provider_state=str(
                        item.get("provider_state", "DATA_UNAVAILABLE")
                    ),
                    last_trade_time=item.get(
                        "last_trade_time",
                    ),
                    provider_timestamp=item.get(
                        "provider_timestamp",
                    ),
                )
            )

        MarketQuote.objects.bulk_create(
            objects,
            batch_size=500,
            update_conflicts=True,
            unique_fields=[
                "symbol",
                "exchange",
            ],
            update_fields=[
                "company",
                "instrument_key",
                "company_name",
                "last_price",
                "open_price",
                "high_price",
                "low_price",
                "previous_close",
                "change",
                "change_percent",
                "volume",
                "traded_value",
                "market_status",
                "provider_state",
                "last_trade_time",
                "provider_timestamp",
                "updated_at",
            ],
        )

        return len(objects)
