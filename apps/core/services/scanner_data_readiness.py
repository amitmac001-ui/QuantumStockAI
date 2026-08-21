from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import Max
from django.utils import timezone

from apps.companies.models import Company
from apps.market.models import (
    CloudBenchmarkCandle,
    CloudDailyCandle,
    CloudQuoteSnapshot,
    MarketOHLC,
    MarketQuote,
)
from apps.market.services.benchmark_history_service import BenchmarkHistoryService
from apps.market.services.daily_history_sync_service import DailyHistorySyncService
from apps.scanner.services.scan_report_cache_service import (
    InvalidScanCache,
    ScanReportCacheService,
)


IST = ZoneInfo("Asia/Kolkata")
DATA_UNAVAILABLE = "DATA_UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class ScannerReadinessSnapshot:
    mode: str
    active_eligible_instruments: int
    latest_stock_session: date | None
    latest_benchmark_session: date | None
    expected_latest_completed_session: date
    aligned_session: date | None
    distinct_stock_instruments: int
    distinct_quote_instruments: int
    stock_coverage: float
    quote_coverage: float
    latest_quote_timestamp: datetime | None = None
    report_instruments: int | None = None
    report_coverage: float | None = None
    cache_error: str | None = None
    provider_empty: str = DATA_UNAVAILABLE
    provider_failed: str = DATA_UNAVAILABLE


class ScannerDataReadinessService:
    """Read-only, eligible-universe readiness diagnostics for scanner publishing."""

    MIN_STOCK_COVERAGE = 0.95
    MIN_QUOTE_COVERAGE = 0.95
    # Two independent 95% input sets can overlap by as little as 90%.
    MIN_REPORT_COVERAGE = 0.90
    MARKET_CLOSE_GRACE = time(16, 0)

    @classmethod
    def expected_latest_completed_session(cls, now: datetime | None = None) -> date:
        local_now = (now or timezone.now()).astimezone(IST)
        candidate = local_now.date()
        if local_now.time() < cls.MARKET_CLOSE_GRACE:
            candidate -= timedelta(days=1)
        while candidate.weekday() >= 5:
            candidate -= timedelta(days=1)
        return candidate

    @staticmethod
    def _coverage(covered: int, eligible: int) -> float:
        return (covered / eligible) if eligible > 0 else 0.0

    @staticmethod
    def eligible_companies():
        return Company.objects.filter(
            exchange="NSE",
            is_active=True,
            instrument_status=Company.InstrumentStatus.ACTIVE,
        ).exclude(upstox_instrument_key="")

    @classmethod
    def collect(
        cls,
        *,
        now: datetime | None = None,
        check_cache: bool = False,
    ) -> ScannerReadinessSnapshot:
        eligible = cls.eligible_companies()
        eligible_count = eligible.values("id").distinct().count()
        expected = cls.expected_latest_completed_session(now)

        if settings.CLOUD_COMPACT_MARKET_DATA:
            stock_query = CloudDailyCandle.objects.filter(company__in=eligible)
            latest_stock = stock_query.aggregate(latest=Max("session_date"))["latest"]
            latest_benchmark = CloudBenchmarkCandle.objects.aggregate(
                latest=Max("session_date")
            )["latest"]
            aligned = latest_stock if latest_stock == latest_benchmark else None
            stock_count = (
                stock_query.filter(session_date=aligned)
                .values("company_id").distinct().count()
                if aligned else 0
            )
            eligible_quotes = CloudQuoteSnapshot.objects.filter(company__in=eligible)
            quote_count = eligible_quotes.values("company_id").distinct().count()
            latest_quote = eligible_quotes.aggregate(
                latest=Max("provider_timestamp")
            )["latest"]
            mode = "cloud_compact"
        else:
            eligible_symbols = eligible.values("symbol")
            stock_query = MarketOHLC.objects.filter(
                interval=MarketOHLC.Interval.D1,
                exchange="NSE",
                symbol__in=eligible_symbols,
            )
            latest_stock_time = stock_query.aggregate(latest=Max("candle_time"))["latest"]
            latest_stock = (
                DailyHistorySyncService.session_date(latest_stock_time)
                if latest_stock_time else None
            )
            benchmark_time = MarketOHLC.objects.filter(
                symbol=BenchmarkHistoryService.SYMBOL,
                exchange=BenchmarkHistoryService.EXCHANGE,
                interval=MarketOHLC.Interval.D1,
            ).aggregate(latest=Max("candle_time"))["latest"]
            latest_benchmark = (
                DailyHistorySyncService.session_date(benchmark_time)
                if benchmark_time else None
            )
            aligned = latest_stock if latest_stock == latest_benchmark else None
            stock_count = (
                stock_query.filter(candle_time__date=aligned)
                .values("symbol", "exchange").distinct().count()
                if aligned else 0
            )
            eligible_quotes = MarketQuote.objects.filter(
                exchange="NSE", symbol__in=eligible_symbols
            )
            quote_count = eligible_quotes.values("symbol", "exchange").distinct().count()
            latest_quote = eligible_quotes.aggregate(
                latest=Max("provider_timestamp")
            )["latest"]
            mode = "standard"

        report_count: int | None = None
        report_coverage: float | None = None
        cache_error: str | None = None
        if check_cache:
            if aligned is None:
                report_count = 0
                report_coverage = 0.0
                cache_error = "ALIGNED_SESSION_UNAVAILABLE"
            else:
                try:
                    reports, _context = ScanReportCacheService().load(
                        expected_session=aligned
                    )
                    eligible_keys = {
                        (str(exchange).upper(), str(symbol).upper())
                        for exchange, symbol in eligible.values_list("exchange", "symbol")
                    }
                    report_keys = {
                        (
                            str(report.snapshot.exchange or "NSE").upper(),
                            str(report.snapshot.symbol or "").upper(),
                        )
                        for report in reports
                    }
                    report_count = len(report_keys.intersection(eligible_keys))
                    report_coverage = cls._coverage(report_count, eligible_count)
                except InvalidScanCache as exc:
                    report_count = 0
                    report_coverage = 0.0
                    cache_error = type(exc).__name__

        return ScannerReadinessSnapshot(
            mode=mode,
            active_eligible_instruments=eligible_count,
            latest_stock_session=latest_stock,
            latest_benchmark_session=latest_benchmark,
            expected_latest_completed_session=expected,
            aligned_session=aligned,
            distinct_stock_instruments=stock_count,
            distinct_quote_instruments=quote_count,
            stock_coverage=cls._coverage(stock_count, eligible_count),
            quote_coverage=cls._coverage(quote_count, eligible_count),
            latest_quote_timestamp=latest_quote,
            report_instruments=report_count,
            report_coverage=report_coverage,
            cache_error=cache_error,
        )

    @classmethod
    def failures(cls, snapshot: ScannerReadinessSnapshot) -> list[str]:
        failures: list[str] = []
        if snapshot.active_eligible_instruments <= 0:
            failures.append("ELIGIBLE_UNIVERSE_EMPTY")
        if snapshot.aligned_session is None:
            failures.append("STOCK_BENCHMARK_SESSION_MISMATCH")
        elif snapshot.aligned_session != snapshot.expected_latest_completed_session:
            failures.append("STALE_SESSION")
        if snapshot.stock_coverage < cls.MIN_STOCK_COVERAGE:
            failures.append("INCOMPLETE_STOCK_COVERAGE")
        if snapshot.quote_coverage < cls.MIN_QUOTE_COVERAGE:
            failures.append("INCOMPLETE_QUOTE_COVERAGE")
        if snapshot.report_coverage is not None:
            if snapshot.cache_error:
                failures.append("SCAN_CACHE_INVALID")
            if snapshot.report_coverage < cls.MIN_REPORT_COVERAGE:
                failures.append("INCOMPLETE_REPORT_COVERAGE")
        return failures

    @staticmethod
    def _value(value: Any) -> str:
        if value is None:
            return DATA_UNAVAILABLE
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)

    @classmethod
    def diagnostic_fields(cls, snapshot: ScannerReadinessSnapshot) -> str:
        report_count = (
            "NOT_CHECKED" if snapshot.report_instruments is None
            else str(snapshot.report_instruments)
        )
        report_coverage = (
            "NOT_CHECKED" if snapshot.report_coverage is None
            else f"{snapshot.report_coverage * 100:.2f}"
        )
        return " ".join([
            f"mode={snapshot.mode}",
            f"active_eligible_instruments={snapshot.active_eligible_instruments}",
            f"distinct_stock_instruments={snapshot.distinct_stock_instruments}",
            f"distinct_quote_instruments={snapshot.distinct_quote_instruments}",
            f"stock_coverage_pct={snapshot.stock_coverage * 100:.2f}",
            f"quote_coverage_pct={snapshot.quote_coverage * 100:.2f}",
            f"report_instruments={report_count}",
            f"report_coverage_pct={report_coverage}",
            f"latest_stored_session={cls._value(snapshot.latest_stock_session)}",
            f"latest_benchmark_session={cls._value(snapshot.latest_benchmark_session)}",
            "expected_latest_completed_nse_session="
            f"{snapshot.expected_latest_completed_session.isoformat()}",
            f"aligned_session={cls._value(snapshot.aligned_session)}",
            f"latest_quote_timestamp={cls._value(snapshot.latest_quote_timestamp)}",
            f"provider_empty={snapshot.provider_empty}",
            f"provider_failed={snapshot.provider_failed}",
        ])
