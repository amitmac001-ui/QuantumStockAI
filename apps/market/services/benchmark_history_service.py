from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import pandas as pd
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.market.models import CloudBenchmarkCandle, MarketOHLC
from apps.market.providers.historical_client import HistoricalClient


@dataclass(frozen=True, slots=True)
class BenchmarkSyncResult:
    instrument_key: str
    received: int
    stored: int
    created: int
    updated: int
    oldest: Any | None
    latest: Any | None


class BenchmarkHistoryService:
    """Idempotent NIFTY 50-only historical candle sync."""

    SYMBOL = "NIFTY 50"
    EXCHANGE = "NSE"
    INSTRUMENT_KEY = "NSE_INDEX|Nifty 50"
    INTERVAL = MarketOHLC.Interval.D1
    PROVIDER_INTERVAL = "day"
    DEFAULT_CALENDAR_DAYS = 500

    def __init__(self, client: HistoricalClient | None = None):
        self.client = client or HistoricalClient()

    @staticmethod
    def _aware_timestamp(value: Any):
        timestamp = pd.Timestamp(value).to_pydatetime()
        return (
            timezone.make_aware(timestamp)
            if timezone.is_naive(timestamp)
            else timestamp
        )

    @classmethod
    def _clean_frame(cls, frame: pd.DataFrame) -> pd.DataFrame:
        required = {"timestamp", "open", "high", "low", "close", "volume"}
        if frame.empty or not required.issubset(frame.columns):
            return pd.DataFrame(columns=sorted(required))

        clean = frame.loc[:, list(required)].copy()
        clean["timestamp"] = pd.to_datetime(clean["timestamp"], errors="coerce")
        numeric = ["open", "high", "low", "close", "volume"]
        clean[numeric] = clean[numeric].apply(pd.to_numeric, errors="coerce")
        clean = clean.dropna()
        clean = clean.loc[
            (clean[["open", "high", "low", "close"]] > 0).all(axis=1)
            & (clean["volume"] >= 0)
            & (clean["high"] >= clean[["open", "low", "close"]].max(axis=1))
            & (clean["low"] <= clean[["open", "high", "close"]].min(axis=1))
        ]
        return (
            clean.sort_values("timestamp")
            .drop_duplicates("timestamp", keep="last")
            .reset_index(drop=True)
        )

    @classmethod
    @transaction.atomic
    def persist_frame(cls, frame: pd.DataFrame) -> tuple[int, int]:
        clean = cls._clean_frame(frame)
        if clean.empty:
            return 0, 0

        timestamps = [cls._aware_timestamp(value) for value in clean["timestamp"]]
        existing = set(
            MarketOHLC.objects.filter(
                symbol=cls.SYMBOL,
                exchange=cls.EXCHANGE,
                interval=cls.INTERVAL,
                candle_time__in=timestamps,
            ).values_list("candle_time", flat=True)
        )
        objects = []
        for (_, row), candle_time in zip(clean.iterrows(), timestamps):
            objects.append(
                MarketOHLC(
                    symbol=cls.SYMBOL,
                    exchange=cls.EXCHANGE,
                    interval=cls.INTERVAL,
                    candle_time=candle_time,
                    open=row["open"],
                    high=row["high"],
                    low=row["low"],
                    close=row["close"],
                    volume=int(row["volume"]),
                )
            )

        MarketOHLC.objects.bulk_create(
            objects,
            update_conflicts=True,
            update_fields=["open", "high", "low", "close", "volume"],
            unique_fields=["symbol", "exchange", "interval", "candle_time"],
        )
        created = sum(candle_time not in existing for candle_time in timestamps)
        return created, len(objects) - created

    @classmethod
    def load_frame(cls, limit: int = 0) -> pd.DataFrame:
        queryset = MarketOHLC.objects.filter(
            symbol=cls.SYMBOL,
            exchange=cls.EXCHANGE,
            interval=cls.INTERVAL,
        ).order_by("-candle_time")
        if limit > 0:
            queryset = queryset[:limit]
        rows = list(queryset.values("candle_time", "close"))
        rows.reverse()
        return pd.DataFrame(
            {
                "timestamp": [row["candle_time"] for row in rows],
                "close": [float(row["close"]) for row in rows],
            }
        )

    @classmethod
    def load_ohlcv_frame(cls, limit: int = 0) -> pd.DataFrame:
        if settings.CLOUD_COMPACT_MARKET_DATA:
            queryset = CloudBenchmarkCandle.objects.order_by("-session_date")
            if limit > 0:
                queryset = queryset[:limit]
            rows = list(queryset.values(
                "session_date", "open", "high", "low", "close", "volume"
            ))
            rows.reverse()
            return pd.DataFrame({
                "timestamp": [row["session_date"] for row in rows],
                "open": [float(row["open"]) for row in rows],
                "high": [float(row["high"]) for row in rows],
                "low": [float(row["low"]) for row in rows],
                "close": [float(row["close"]) for row in rows],
                "volume": [int(row["volume"]) for row in rows],
            })
        queryset = MarketOHLC.objects.filter(
            symbol=cls.SYMBOL,
            exchange=cls.EXCHANGE,
            interval=cls.INTERVAL,
        ).order_by("-candle_time")
        if limit > 0:
            queryset = queryset[:limit]
        rows = list(
            queryset.values(
                "candle_time", "open", "high", "low", "close", "volume"
            )
        )
        rows.reverse()
        return pd.DataFrame(
            {
                "timestamp": [row["candle_time"] for row in rows],
                "open": [float(row["open"]) for row in rows],
                "high": [float(row["high"]) for row in rows],
                "low": [float(row["low"]) for row in rows],
                "close": [float(row["close"]) for row in rows],
                "volume": [int(row["volume"]) for row in rows],
            }
        )

    def sync(
        self,
        *,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> BenchmarkSyncResult:
        end = date.fromisoformat(to_date) if to_date else date.today()
        start = (
            date.fromisoformat(from_date)
            if from_date
            else end - timedelta(days=self.DEFAULT_CALENDAR_DAYS)
        )
        response = self.client.candles(
            instrument_key=self.INSTRUMENT_KEY,
            interval=self.PROVIDER_INTERVAL,
            from_date=start.isoformat(),
            to_date=end.isoformat(),
        )
        candles = getattr(getattr(response, "data", None), "candles", []) or []
        received = len(candles)
        frame = self.client.dataframe(candles)
        created, updated = self.persist_frame(frame)

        stored = MarketOHLC.objects.filter(
            symbol=self.SYMBOL,
            exchange=self.EXCHANGE,
            interval=self.INTERVAL,
        )
        return BenchmarkSyncResult(
            instrument_key=self.INSTRUMENT_KEY,
            received=received,
            stored=stored.count(),
            created=created,
            updated=updated,
            oldest=stored.order_by("candle_time").values_list(
                "candle_time", flat=True
            ).first(),
            latest=stored.order_by("-candle_time").values_list(
                "candle_time", flat=True
            ).first(),
        )


benchmark_history_service_class = BenchmarkHistoryService
