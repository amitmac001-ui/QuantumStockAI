from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date, datetime, time as datetime_time, timedelta
from typing import Any, Callable
from zoneinfo import ZoneInfo

import pandas as pd
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.companies.models import Company
from apps.market.models import MarketOHLC
from apps.market.providers.historical_client import HistoricalClient
from apps.market.services.benchmark_history_service import BenchmarkHistoryService


IST = ZoneInfo("Asia/Kolkata")


@dataclass(frozen=True, slots=True)
class SampleCandleStatus:
    symbol: str
    latest_daily_session: date | None
    candle_count_available: int
    latest_close: float | None
    latest_volume: int | None
    aligned_with_benchmark: bool | None
    fresh: bool


@dataclass(slots=True)
class DailyHistorySyncResult:
    eligible_stocks: int = 0
    already_current: int = 0
    stocks_updated: int = 0
    candles_inserted: int = 0
    candles_updated: int = 0
    stocks_failed: int = 0
    stocks_without_instrument_key: int = 0
    stocks_without_history: int = 0
    inactive_stocks_excluded: int = 0
    suspended_stocks_excluded: int = 0
    invalid_instruments_excluded: int = 0
    invalid_instrument_failures: int = 0
    latest_session_date: date | None = None
    oldest_stale_date: date | None = None
    remaining_stale_stocks: int = 0
    duplicate_daily_candles: int = 0
    failures: list[str] = field(default_factory=list)
    samples: list[SampleCandleStatus] = field(default_factory=list)


class DailyHistorySyncService:
    """Incremental, resumable Upstox daily-candle sync for active NSE equities."""

    SAMPLE_SYMBOLS = ("ATHERENERG", "DMART", "ALLCARGO", "FEDERALBNK", "ACSTECH")
    PROVIDER_INTERVAL = "day"
    INITIAL_LOOKBACK_DAYS = 420
    SESSION_DISCOVERY_DAYS = 21
    MARKET_CLOSE_GRACE = datetime_time(16, 0)
    MAX_RETRIES = 3
    DEFAULT_REQUEST_INTERVAL_SECONDS = 0.13

    def __init__(
        self,
        client: HistoricalClient | None = None,
        *,
        sleep: Callable[[float], None] = time.sleep,
        request_interval_seconds: float = DEFAULT_REQUEST_INTERVAL_SECONDS,
        now: datetime | None = None,
    ):
        self.client = client or HistoricalClient()
        self.sleep = sleep
        self.request_interval_seconds = max(float(request_interval_seconds), 0.0)
        self.now = now or timezone.now()

    @staticmethod
    def session_date(value: Any) -> date:
        timestamp = pd.Timestamp(value)
        if timestamp.tzinfo is None:
            timestamp = timestamp.tz_localize(IST)
        else:
            timestamp = timestamp.tz_convert(IST)
        return timestamp.date()

    @staticmethod
    def canonical_session_timestamp(session: date) -> datetime:
        return datetime.combine(session, datetime_time.min, tzinfo=IST)

    @classmethod
    def is_fresh(cls, candle_time: datetime | None, latest_session: date) -> bool:
        return bool(candle_time and cls.session_date(candle_time) >= latest_session)

    @staticmethod
    def _status_code(exc: Exception) -> int | None:
        value = getattr(exc, "status", None) or getattr(exc, "status_code", None)
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @classmethod
    def _retryable(cls, exc: Exception) -> bool:
        status = cls._status_code(exc)
        return status is None or status == 429 or status >= 500

    def _request(self, instrument_key: str, start: date, end: date):
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                response = self.client.candles(
                    instrument_key=instrument_key,
                    interval=self.PROVIDER_INTERVAL,
                    from_date=start.isoformat(),
                    to_date=end.isoformat(),
                )
                if self.request_interval_seconds:
                    self.sleep(self.request_interval_seconds)
                return response
            except Exception as exc:
                if attempt >= self.MAX_RETRIES or not self._retryable(exc):
                    raise
                self.sleep(min(2 ** (attempt - 1), 8))

    def _frame_from_response(self, response: Any) -> pd.DataFrame:
        candles = getattr(getattr(response, "data", None), "candles", []) or []
        return self.client.dataframe(candles)

    @classmethod
    def _clean_frame(
        cls, frame: pd.DataFrame, *, start: date, end: date
    ) -> pd.DataFrame:
        required = ["timestamp", "open", "high", "low", "close", "volume"]
        output_columns = [
            *required,
            "provider_timestamp",
            "data_quality_flags",
            "session_date",
            "candle_time",
        ]
        if frame.empty or not set(required).issubset(frame.columns):
            return pd.DataFrame(columns=output_columns)

        quality_column = next(
            (
                column
                for column in ("data_quality_flags", "data_quality")
                if column in frame.columns
            ),
            None,
        )
        selected = [*required, *([quality_column] if quality_column else [])]
        clean = frame.loc[:, selected].copy()
        clean["timestamp"] = pd.to_datetime(
            clean["timestamp"], errors="coerce", utc=True
        )
        numeric = ["open", "high", "low", "close", "volume"]
        clean[numeric] = clean[numeric].apply(pd.to_numeric, errors="coerce")
        clean = clean.dropna(subset=required)
        clean = clean.loc[
            (clean[["open", "high", "low", "close"]] > 0).all(axis=1)
            & (clean["volume"] >= 0)
            & (clean["high"] >= clean[["open", "low", "close"]].max(axis=1))
            & (clean["low"] <= clean[["open", "high", "close"]].min(axis=1))
        ].copy()
        if clean.empty:
            return pd.DataFrame(columns=output_columns)
        clean["session_date"] = clean["timestamp"].map(cls.session_date)
        clean = clean.loc[clean["session_date"].between(start, end)]
        clean = clean.sort_values("timestamp").drop_duplicates(
            "session_date", keep="last"
        )
        clean["provider_timestamp"] = clean["timestamp"]
        if quality_column:
            clean["data_quality_flags"] = clean[quality_column].map(
                cls._normalize_quality_flags
            )
        else:
            clean["data_quality_flags"] = [[] for _ in range(len(clean))]
        clean["candle_time"] = clean["session_date"].map(
            cls.canonical_session_timestamp
        )
        return clean.reset_index(drop=True)

    @staticmethod
    def _normalize_quality_flags(value: Any) -> list[str]:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return []
        values = value if isinstance(value, (list, tuple, set)) else [value]
        return list(
            dict.fromkeys(str(item).strip() for item in values if str(item).strip())
        )

    def resolve_latest_completed_session(self) -> tuple[date, pd.DataFrame]:
        local_now = self.now.astimezone(IST)
        end = local_now.date()
        start = end - timedelta(days=self.SESSION_DISCOVERY_DAYS)
        frame = self._clean_frame(
            self._frame_from_response(
                self._request(BenchmarkHistoryService.INSTRUMENT_KEY, start, end)
            ),
            start=start,
            end=end,
        )
        if frame.empty:
            raise RuntimeError("Upstox returned no completed NIFTY 50 daily session.")

        if local_now.time() < self.MARKET_CLOSE_GRACE:
            frame = frame.loc[frame["session_date"] < local_now.date()]
        if frame.empty:
            raise RuntimeError("No completed NIFTY 50 session exists in provider response.")

        latest_session = max(frame["session_date"])
        benchmark_frame = frame.loc[frame["session_date"] <= latest_session]
        BenchmarkHistoryService.persist_frame(
            benchmark_frame.rename(columns={"candle_time": "normalized_timestamp"})
            .assign(timestamp=lambda value: value["normalized_timestamp"])
            .loc[:, ["timestamp", "open", "high", "low", "close", "volume"]]
        )
        return latest_session, benchmark_frame

    @staticmethod
    def _latest_map() -> dict[tuple[str, str], datetime]:
        rows = (
            MarketOHLC.objects.filter(interval=MarketOHLC.Interval.D1)
            .values("symbol", "exchange")
            .annotate(latest=Max("candle_time"))
        )
        return {(row["symbol"], row["exchange"]): row["latest"] for row in rows}

    @classmethod
    @transaction.atomic
    def persist_stock_frame(
        cls,
        *,
        symbol: str,
        exchange: str,
        frame: pd.DataFrame,
        start: date,
        end: date,
    ) -> tuple[int, int]:
        clean = cls._clean_frame(frame, start=start, end=end)
        if clean.empty:
            return 0, 0

        timestamps = list(clean["candle_time"])
        existing = set(
            MarketOHLC.objects.filter(
                symbol=symbol,
                exchange=exchange,
                interval=MarketOHLC.Interval.D1,
                candle_time__in=timestamps,
            ).values_list("candle_time", flat=True)
        )
        objects = [
            MarketOHLC(
                symbol=symbol,
                exchange=exchange,
                interval=MarketOHLC.Interval.D1,
                candle_time=row["candle_time"],
                provider_timestamp=row["provider_timestamp"],
                data_quality_flags=row["data_quality_flags"],
                open=row["open"],
                high=row["high"],
                low=row["low"],
                close=row["close"],
                volume=int(row["volume"]),
            )
            for _, row in clean.iterrows()
        ]
        MarketOHLC.objects.bulk_create(
            objects,
            batch_size=500,
            update_conflicts=True,
            update_fields=[
                "open",
                "high",
                "low",
                "close",
                "volume",
                "provider_timestamp",
                "data_quality_flags",
            ],
            unique_fields=["symbol", "exchange", "interval", "candle_time"],
        )
        created = sum(timestamp not in existing for timestamp in timestamps)
        return created, len(objects) - created

    @classmethod
    def sample_statuses(cls, latest_session: date) -> list[SampleCandleStatus]:
        benchmark_dates = {
            cls.session_date(value)
            for value in MarketOHLC.objects.filter(
                symbol=BenchmarkHistoryService.SYMBOL,
                exchange=BenchmarkHistoryService.EXCHANGE,
                interval=MarketOHLC.Interval.D1,
            ).values_list("candle_time", flat=True)
        }
        statuses = []
        for symbol in cls.SAMPLE_SYMBOLS:
            queryset = MarketOHLC.objects.filter(
                symbol=symbol, exchange="NSE", interval=MarketOHLC.Interval.D1
            )
            latest = queryset.order_by("-candle_time").first()
            session = cls.session_date(latest.candle_time) if latest else None
            statuses.append(
                SampleCandleStatus(
                    symbol=symbol,
                    latest_daily_session=session,
                    candle_count_available=queryset.count(),
                    latest_close=float(latest.close) if latest else None,
                    latest_volume=int(latest.volume) if latest else None,
                    aligned_with_benchmark=(session in benchmark_dates) if session else None,
                    fresh=bool(session and session >= latest_session),
                )
            )
        return statuses

    def sync(
        self,
        *,
        latest_session: date | None = None,
        limit: int = 0,
        symbols: list[str] | tuple[str, ...] | None = None,
        progress: Callable[[int, int, DailyHistorySyncResult], None] | None = None,
    ) -> DailyHistorySyncResult:
        if latest_session is None:
            latest_session, _ = self.resolve_latest_completed_session()

        universe = Company.objects.filter(exchange="NSE")
        requested_symbols = {
            str(symbol).strip().upper()
            for symbol in (symbols or [])
            if str(symbol).strip()
        }
        if requested_symbols:
            universe = universe.filter(symbol__in=requested_symbols)

        excluded = list(
            universe.exclude(
                is_active=True,
                instrument_status=Company.InstrumentStatus.ACTIVE,
            ).only("instrument_status")
        )
        companies = list(
            universe.filter(
                is_active=True,
                instrument_status=Company.InstrumentStatus.ACTIVE,
            )
            .only("symbol", "exchange", "upstox_instrument_key")
            .order_by("symbol")
        )
        result = DailyHistorySyncResult(
            eligible_stocks=len(companies),
            latest_session_date=latest_session,
            inactive_stocks_excluded=len(excluded),
            suspended_stocks_excluded=sum(
                company.instrument_status == Company.InstrumentStatus.SUSPENDED
                for company in excluded
            ),
            invalid_instruments_excluded=sum(
                company.instrument_status == Company.InstrumentStatus.INVALID
                for company in excluded
            ),
        )
        latest_by_key = self._latest_map()
        stale_dates = [
            self.session_date(latest_by_key[(company.symbol, company.exchange)])
            for company in companies
            if (company.symbol, company.exchange) in latest_by_key
            and self.session_date(latest_by_key[(company.symbol, company.exchange)])
            < latest_session
        ]
        result.oldest_stale_date = min(stale_dates) if stale_dates else None

        processable = companies[:limit] if limit > 0 else companies
        for index, company in enumerate(processable, start=1):
            instrument_key = str(company.upstox_instrument_key or "").strip()
            if not instrument_key:
                result.stocks_without_instrument_key += 1
                if progress:
                    progress(index, len(processable), result)
                continue

            key = (company.symbol, company.exchange)
            latest = latest_by_key.get(key)
            if self.is_fresh(latest, latest_session):
                result.already_current += 1
                if progress:
                    progress(index, len(processable), result)
                continue

            start = (
                self.session_date(latest) + timedelta(days=1)
                if latest
                else latest_session - timedelta(days=self.INITIAL_LOOKBACK_DAYS)
            )
            try:
                response = self._request(instrument_key, start, latest_session)
                frame = self._frame_from_response(response)
                clean = self._clean_frame(frame, start=start, end=latest_session)
                if clean.empty:
                    raise RuntimeError(
                        "provider returned no valid daily candles in the missing range"
                    )
                created, updated = self.persist_stock_frame(
                    symbol=company.symbol,
                    exchange=company.exchange,
                    frame=frame,
                    start=start,
                    end=latest_session,
                )
                result.candles_inserted += created
                result.candles_updated += updated
                if created or updated:
                    result.stocks_updated += 1
                    latest_by_key[key] = self.canonical_session_timestamp(
                        max(clean["session_date"])
                    )
            except Exception as exc:
                result.stocks_failed += 1
                if self._status_code(exc) in {400, 404, 422}:
                    result.invalid_instrument_failures += 1
                result.failures.append(f"{company.symbol}: {exc}")

            if progress:
                progress(index, len(processable), result)

        result.remaining_stale_stocks = sum(
            latest_by_key.get((company.symbol, company.exchange)) is not None
            and not self.is_fresh(
                latest_by_key[(company.symbol, company.exchange)], latest_session
            )
            for company in companies
            if str(company.upstox_instrument_key or "").strip()
        )
        result.stocks_without_history = sum(
            latest_by_key.get((company.symbol, company.exchange)) is None
            for company in companies
            if str(company.upstox_instrument_key or "").strip()
        )
        result.samples = self.sample_statuses(latest_session)
        return result
