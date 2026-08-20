from __future__ import annotations

import json
import os
from dataclasses import asdict, fields
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable

from django.conf import settings
from django.db.models import Max
from django.utils import timezone

from apps.market.models import CloudBenchmarkCandle, CloudDailyCandle, MarketOHLC
from apps.market.services.benchmark_history_service import BenchmarkHistoryService
from apps.market.services.daily_history_sync_service import DailyHistorySyncService
from apps.companies.models import Company
from apps.scanner.engine.decision_engine import ScanReport, StockSnapshot, StrategyResult


class InvalidScanCache(RuntimeError):
    pass


def _encode(value: Any) -> Any:
    if isinstance(value, datetime):
        return {"__type__": "datetime", "value": value.isoformat()}
    if isinstance(value, date):
        return {"__type__": "date", "value": value.isoformat()}
    if isinstance(value, Decimal):
        return {"__type__": "decimal", "value": str(value)}
    if isinstance(value, tuple):
        return {"__type__": "tuple", "value": [_encode(item) for item in value]}
    if isinstance(value, list):
        return [_encode(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _encode(item) for key, item in value.items()}
    return value


def _decode(value: Any) -> Any:
    if isinstance(value, list):
        return [_decode(item) for item in value]
    if not isinstance(value, dict):
        return value
    marker = value.get("__type__")
    if marker == "datetime":
        return datetime.fromisoformat(value["value"])
    if marker == "date":
        return date.fromisoformat(value["value"])
    if marker == "decimal":
        return Decimal(value["value"])
    if marker == "tuple":
        return tuple(_decode(item) for item in value["value"])
    return {key: _decode(item) for key, item in value.items()}


class ScanReportCacheService:
    """Atomic, session-bound cache of completed scanner reports."""

    VERSION = 1

    def __init__(self, path: str | Path | None = None):
        configured = getattr(settings, "SCAN_REPORT_CACHE_PATH", "")
        self.path = Path(
            path or configured or Path(settings.BASE_DIR) / "data" / "latest_scan_reports.json"
        )

    @staticmethod
    def _session(value: Any) -> date:
        if isinstance(value, datetime):
            return DailyHistorySyncService.session_date(value)
        if isinstance(value, date):
            return value
        try:
            return date.fromisoformat(str(value))
        except (TypeError, ValueError) as exc:
            raise InvalidScanCache(f"Invalid scanner session: {value}") from exc

    def save(
        self,
        reports: Iterable[ScanReport],
        *,
        session: Any,
        session_context: dict[str, Any],
    ) -> Path:
        scanner_session = self._session(session)
        context_session = self._session(session_context.get("scanner_session"))
        if scanner_session != context_session:
            raise InvalidScanCache("Cached session does not equal scanner session.")
        report_list = list(reports)
        for report in report_list:
            report_session = report.snapshot.latest_daily_session
            if report_session is not None and self._session(report_session) != scanner_session:
                raise InvalidScanCache(
                    f"Report session mismatch for {report.snapshot.symbol}."
                )
        payload = {
            "version": self.VERSION,
            "session": scanner_session.isoformat(),
            "generated_at": timezone.now(),
            "session_context": session_context,
            "reports": [asdict(report) for report in report_list],
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(_encode(payload), sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        os.replace(temporary, self.path)
        return self.path

    @staticmethod
    def _report(data: dict[str, Any]) -> ScanReport:
        values = dict(data)
        values["snapshot"] = StockSnapshot.from_mapping(values["snapshot"])
        values["strategies"] = [StrategyResult(**item) for item in values["strategies"]]
        allowed = {item.name for item in fields(ScanReport)}
        return ScanReport(**{key: value for key, value in values.items() if key in allowed})

    def load(self, *, expected_session: Any) -> tuple[list[ScanReport], dict[str, Any]]:
        try:
            payload = _decode(json.loads(self.path.read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError) as exc:
            raise InvalidScanCache(f"Scan cache unavailable or invalid: {exc}") from exc
        if payload.get("version") != self.VERSION:
            raise InvalidScanCache("Unsupported scan cache version.")
        cached_session = self._session(payload.get("session"))
        required_session = self._session(expected_session)
        context = dict(payload.get("session_context") or {})
        if (
            cached_session != required_session
            or self._session(context.get("scanner_session")) != required_session
        ):
            raise InvalidScanCache(
                f"Stale scan cache: cached={cached_session}, expected={required_session}."
            )
        context["cache_generated_at"] = payload.get("generated_at")
        return [self._report(item) for item in payload.get("reports", [])], context

    @staticmethod
    def latest_aligned_session() -> date:
        eligible = Company.objects.filter(
            exchange="NSE", is_active=True,
            instrument_status=Company.InstrumentStatus.ACTIVE,
        ).exclude(upstox_instrument_key="")
        if settings.CLOUD_COMPACT_MARKET_DATA:
            stock_session = CloudDailyCandle.objects.filter(
                company__in=eligible
            ).aggregate(latest=Max("session_date"))["latest"]
            benchmark_session = CloudBenchmarkCandle.objects.aggregate(
                latest=Max("session_date")
            )["latest"]
        else:
            stock_time = MarketOHLC.objects.filter(
                interval=MarketOHLC.Interval.D1,
                exchange="NSE",
                symbol__in=eligible.values("symbol"),
            ).exclude(
                symbol=BenchmarkHistoryService.SYMBOL
            ).aggregate(latest=Max("candle_time"))["latest"]
            benchmark_time = MarketOHLC.objects.filter(
                symbol=BenchmarkHistoryService.SYMBOL,
                exchange=BenchmarkHistoryService.EXCHANGE,
                interval=MarketOHLC.Interval.D1,
            ).aggregate(latest=Max("candle_time"))["latest"]
            stock_session = (
                DailyHistorySyncService.session_date(stock_time) if stock_time else None
            )
            benchmark_session = (
                DailyHistorySyncService.session_date(benchmark_time)
                if benchmark_time else None
            )
        if stock_session is None or benchmark_session is None:
            raise InvalidScanCache("Aligned stock/benchmark session unavailable.")
        if stock_session != benchmark_session:
            raise InvalidScanCache(
                f"Stock/benchmark session mismatch: {stock_session}/{benchmark_session}."
            )
        return stock_session

    def load_valid(self) -> tuple[list[ScanReport], dict[str, Any]]:
        return self.load(expected_session=self.latest_aligned_session())
