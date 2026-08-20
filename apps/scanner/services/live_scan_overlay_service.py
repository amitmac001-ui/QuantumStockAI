from __future__ import annotations

import copy
from collections.abc import Iterable

from django.conf import settings

from apps.market.models import CloudQuoteSnapshot, MarketQuote
from apps.scanner.engine.decision_engine import ScanReport


class LiveScanOverlayService:
    """Overlay persisted quotes only; structural/scoring values stay frozen."""

    @staticmethod
    def _key(exchange, symbol):
        return str(exchange or "NSE").upper(), str(symbol or "").upper()

    @classmethod
    def overlay_reports(cls, reports: Iterable[ScanReport]) -> list[ScanReport]:
        report_list = list(reports)
        if not report_list:
            return []
        symbols = {str(report.snapshot.symbol).upper() for report in report_list}
        if settings.CLOUD_COMPACT_MARKET_DATA:
            queryset = CloudQuoteSnapshot.objects.select_related("company").filter(
                company__symbol__in=symbols
            )
        else:
            queryset = MarketQuote.objects.filter(symbol__in=symbols)
        quotes = {
            cls._key(quote.exchange, quote.symbol): quote for quote in queryset
        }
        overlaid = []
        for report in report_list:
            item = copy.deepcopy(report)
            stock = item.snapshot
            quote = quotes.get(cls._key(stock.exchange, stock.symbol))
            if quote is not None:
                for name in (
                    "last_price", "open_price", "high_price", "low_price",
                    "previous_close", "volume", "provider_timestamp",
                    "last_trade_time",
                ):
                    target = "last_trade_timestamp" if name == "last_trade_time" else name
                    value = getattr(quote, name, None)
                    if value is not None:
                        setattr(stock, target, value)
                technical = dict(stock.technical_scanner_fields or {})
                technical["live_price"] = stock.last_price
                stock.technical_scanner_fields = technical
            overlaid.append(item)
        return overlaid
