from __future__ import annotations

from datetime import datetime, timezone as datetime_timezone
from typing import Any

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.market.models import Exchange, MarketStatus
from apps.market.services.market_status_service import MarketStatusService


class QuoteNormalizer:
    """Canonical provider-to-persistence/WebSocket quote schema."""

    @staticmethod
    def provider_timestamp(value: Any):
        if value in (None, ""):
            return None
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            numeric = None
        if numeric is not None:
            if numeric > 10_000_000_000:
                numeric /= 1000.0
            return datetime.fromtimestamp(numeric, tz=datetime_timezone.utc)
        parsed = parse_datetime(str(value))
        if parsed is None:
            return None
        return timezone.make_aware(parsed) if timezone.is_naive(parsed) else parsed

    @classmethod
    def trade_timestamp(cls, value: Any):
        if value in (None, ""):
            return None
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return cls.provider_timestamp(value)
        if numeric > 10_000_000_000:
            numeric /= 1000.0
        return datetime.fromtimestamp(numeric, tz=datetime_timezone.utc)

    @staticmethod
    def symbol(response_key: str, item: Any, symbol_hint: str = "") -> str:
        supplied = str(getattr(item, "symbol", "") or "").strip().upper()
        if supplied and supplied != "NA":
            return supplied
        if symbol_hint:
            return str(symbol_hint).strip().upper()
        return str(response_key).split(":")[-1].split("|")[-1].strip().upper()

    @classmethod
    def normalize(
        cls,
        *,
        response_key: str,
        item: Any,
        instrument_key: str,
        symbol_hint: str = "",
        company=None,
        company_name: str = "",
        exchange: str = "",
        now=None,
    ) -> dict[str, Any]:
        symbol = cls.symbol(response_key, item, symbol_hint)
        ohlc = getattr(item, "ohlc", None)
        last_price = float(getattr(item, "last_price", 0) or 0)
        net_change = float(getattr(item, "net_change", 0) or 0)
        previous_close = last_price - net_change
        if previous_close <= 0:
            previous_close = float(getattr(ohlc, "close", 0) or 0)
        if previous_close <= 0:
            previous_close = last_price
        change = net_change if net_change else last_price - previous_close
        provider_timestamp = cls.provider_timestamp(getattr(item, "timestamp", None))
        last_trade_time = cls.trade_timestamp(
            getattr(item, "last_trade_time", None)
        )
        freshness = MarketStatusService(now=now).for_provider_timestamp(
            provider_timestamp,
            session=(
                last_trade_time.astimezone(timezone.get_current_timezone()).date()
                if last_trade_time else None
            ),
        )
        resolved_exchange = str(exchange or "").strip().upper()
        if not resolved_exchange:
            resolved_exchange = (
                Exchange.BSE
                if str(instrument_key or response_key).upper().startswith("BSE")
                else Exchange.NSE
            )
        return {
            "symbol": symbol,
            "company": company,
            "company_name": company_name or getattr(company, "name", "") or symbol,
            "instrument_key": str(instrument_key or response_key).strip(),
            "exchange": resolved_exchange,
            "last_price": last_price,
            "open_price": float(getattr(ohlc, "open", 0) or 0),
            "high_price": float(getattr(ohlc, "high", 0) or 0),
            "low_price": float(getattr(ohlc, "low", 0) or 0),
            "previous_close": previous_close,
            "change": change,
            "change_percent": (change / previous_close * 100) if previous_close else 0,
            "volume": int(getattr(item, "volume", 0) or 0),
            "traded_value": 0,
            "provider_timestamp": provider_timestamp,
            "last_trade_time": last_trade_time,
            "market_status": (
                MarketStatus.OPEN
                if freshness.status == MarketStatusService.LIVE
                else MarketStatus.CLOSED
            ),
            "provider_state": freshness.status,
        }
