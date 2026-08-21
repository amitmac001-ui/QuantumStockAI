from __future__ import annotations

import logging
import math
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from time import perf_counter
from typing import Any, Iterable, Sequence

import gspread
from django.conf import settings
from django.utils import timezone

from apps.core.services.google_sheet_base import GoogleSheetBase
from apps.scanner.engine.decision_engine import ScanReport

logger = logging.getLogger(__name__)

DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
NOT_SUPPORTED = "NOT_SUPPORTED"


class EmptyScannerReportSet(RuntimeError):
    pass


class WorksheetHeaderMismatch(RuntimeError):
    pass


def _attr(value: Any, name: str, default=None):
    return getattr(value, name, default)


def _display(value: Any, unavailable: str = DATA_UNAVAILABLE):
    if value is None or value == "":
        return unavailable
    if isinstance(value, float) and not math.isfinite(value):
        return unavailable
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _positive(value: Any):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return DATA_UNAVAILABLE
    if not math.isfinite(number) or number <= 0:
        return DATA_UNAVAILABLE
    return int(number) if number.is_integer() else number


def _yes_no(value: Any):
    if value is None:
        return DATA_UNAVAILABLE
    return "YES" if value is True else "NO"


def _detected(value: Any):
    if value is None:
        return DATA_UNAVAILABLE
    return "DETECTED" if value is True else "NOT_DETECTED"


def _first_present(*values: Any):
    for value in values:
        if value is not None and value != "":
            return value
    return None


def _join(*groups: Iterable[Any] | None):
    values: list[str] = []
    for group in groups:
        for value in group or []:
            text = str(value).strip()
            if text and text not in values:
                values.append(text)
    return " | ".join(values) if values else DATA_UNAVAILABLE


def _quote_time(stock: Any):
    return _first_present(
        _attr(stock, "quote_timestamp"),
        _attr(stock, "provider_timestamp"),
        _attr(stock, "last_trade_timestamp"),
    )


def _age(stock: Any, now: datetime):
    supplied = _attr(stock, "data_age_seconds")
    if supplied is not None:
        try:
            return max(0.0, float(supplied))
        except (TypeError, ValueError):
            return None
    quote_time = _quote_time(stock)
    if not isinstance(quote_time, datetime):
        return None
    if timezone.is_naive(quote_time):
        quote_time = timezone.make_aware(quote_time)
    age = (now - quote_time).total_seconds()
    if age < -300:
        return None
    return max(0.0, age)


def _data_status(stock: Any, now: datetime):
    quality = str(_attr(stock, "data_quality_state", "") or "").upper()
    age = _age(stock, now)
    stale_after = int(getattr(settings, "TECHNICAL_SCANNER_STALE_AFTER_SECONDS", 300))
    if quality == "INVALID":
        return DATA_UNAVAILABLE
    if quality == "STALE" or age is None or age > stale_after:
        return "STALE"
    if quality == "PARTIAL":
        return "PARTIAL"
    if quality == "FRESH":
        return "OK"
    return DATA_UNAVAILABLE


def _unique_reports(reports: Iterable[ScanReport]) -> list[ScanReport]:
    unique: dict[tuple[str, str], ScanReport] = {}
    for report in reports:
        key = (
            str(_attr(report.snapshot, "exchange", "NSE") or "NSE").upper(),
            str(_attr(report.snapshot, "symbol", "") or "").upper(),
        )
        if key[1] and key not in unique:
            unique[key] = report
    return list(unique.values())


def _pattern_values(stock: Any):
    return {
        "VCP": _attr(stock, "vcp_detected"),
        "Flat Base": _attr(stock, "flat_base"),
        "Cup & Handle": NOT_SUPPORTED,
        "Double Bottom": NOT_SUPPORTED,
        "Ascending Triangle": _attr(stock, "ascending_triangle"),
        "Bull Flag": NOT_SUPPORTED,
        "Darvas Box": _attr(stock, "darvas_consolidation"),
        "Head & Shoulders": NOT_SUPPORTED,
    }


def _primary_pattern(stock: Any):
    supported = _pattern_values(stock)
    for name, value in supported.items():
        if value is True:
            return name
    if any(value is False for value in supported.values()):
        return "NOT_DETECTED"
    return DATA_UNAVAILABLE


class TechnicalScannerWorkbookProjection:
    HEADERS = (
        "Company", "Ticker", "Price", "Updated At", "20 SMA", "Cross 20 SMA",
        "20 EMA", "Cross 20 EMA", "50 SMA", "Cross 50 SMA", "50 EMA",
        "Cross 50 EMA", "100 SMA", "Cross 100 SMA", "100 EMA",
        "Cross 100 EMA", "200 SMA", "Cross 200 SMA", "200 EMA",
        "Cross 200 EMA", "VWAP", "RSI 5", "RSI 9", "RSI 14", "RSI 21",
        "RS 1M", "RS 3M", "RS 6M", "RS 12M", "MACD", "MACD Signal",
        "MACD Hist", "MACD Bullish Cross", "BB Upper", "BB Mid", "BB Lower",
        "ATR 14", "ADX 14", "VCP", "Flat Base", "Cup & Handle",
        "Double Bottom", "Ascending Triangle", "Bull Flag", "Darvas Box",
        "Head & Shoulders", "Pattern Score", "Data Status", "Source", "Notes",
    )

    @classmethod
    def rows(cls, reports: Iterable[ScanReport], *, projected_at=None) -> list[list[Any]]:
        now = projected_at or timezone.now()
        output: list[list[Any]] = []
        reports_by_ticker = sorted(
            _unique_reports(reports),
            key=lambda report: (
                str(_attr(report.snapshot, "exchange", "NSE")).upper(),
                str(_attr(report.snapshot, "symbol", "")).upper(),
            ),
        )
        for report in reports_by_ticker:
            stock = report.snapshot
            technical = dict(_attr(stock, "technical_scanner_fields", {}) or {})
            patterns = _pattern_values(stock)
            mapping = {
                "Company": _attr(stock, "company_name") or _attr(stock, "symbol") or DATA_UNAVAILABLE,
                "Ticker": _attr(stock, "symbol") or DATA_UNAVAILABLE,
                "Price": _positive(_attr(stock, "last_price")),
                "Updated At": _display(_first_present(_quote_time(stock), _attr(stock, "calculation_timestamp"))),
                "VWAP": NOT_SUPPORTED,
                "RSI 5": _display(technical.get("rsi_5")),
                "RSI 9": _display(technical.get("rsi_9")),
                "RSI 14": _display(technical.get("rsi_14")),
                "RSI 21": _display(technical.get("rsi_21")),
                "RS 1M": _display(_attr(stock, "rs_1m_pct")),
                "RS 3M": _display(_attr(stock, "rs_3m_pct")),
                "RS 6M": _display(_attr(stock, "rs_6m_pct")),
                "RS 12M": _display(_attr(stock, "rs_12m_pct")),
                "MACD": _display(technical.get("macd")),
                "MACD Signal": _display(technical.get("macd_signal")),
                "MACD Hist": _display(technical.get("macd_histogram")),
                "MACD Bullish Cross": _yes_no(technical.get("macd_bullish_cross")),
                "BB Upper": _display(technical.get("bb_upper")),
                "BB Mid": _display(technical.get("bb_middle")),
                "BB Lower": _display(technical.get("bb_lower")),
                "ATR 14": _display(technical.get("atr_14")),
                "ADX 14": _display(technical.get("adx_14")),
                "VCP": _detected(patterns["VCP"]),
                "Flat Base": _detected(patterns["Flat Base"]),
                "Cup & Handle": patterns["Cup & Handle"],
                "Double Bottom": patterns["Double Bottom"],
                "Ascending Triangle": _detected(patterns["Ascending Triangle"]),
                "Bull Flag": patterns["Bull Flag"],
                "Darvas Box": _detected(patterns["Darvas Box"]),
                "Head & Shoulders": patterns["Head & Shoulders"],
                "Pattern Score": _display(_first_present(
                    _attr(stock, "base_quality_score"),
                    _attr(stock, "vcp_quality_score"),
                    _attr(stock, "pivot_quality_score"),
                )),
                "Data Status": _data_status(stock, now),
                "Source": "PERSISTED_SCANNER_CACHE",
                "Notes": _join(
                    _attr(stock, "data_quality_reason_codes", []),
                    _attr(stock, "setup_risk_flags", []),
                ),
            }
            for period in (20, 50, 100, 200):
                mapping[f"{period} SMA"] = _display(technical.get(f"sma_{period}"))
                mapping[f"Cross {period} SMA"] = _yes_no(
                    technical.get(f"sma_{period}_bullish_cross")
                )
                mapping[f"{period} EMA"] = _display(technical.get(f"ema_{period}"))
                mapping[f"Cross {period} EMA"] = _yes_no(
                    technical.get(f"ema_{period}_bullish_cross")
                )
            row = [mapping[header] for header in cls.HEADERS]
            if len(row) != 50:
                raise ValueError(f"Technical Scanner schema mismatch: {len(row)}/50")
            output.append(row)
        return output


class SwingPrebreakoutProjection:
    HEADERS = (
        "Rank", "Company", "Ticker", "Sector", "Price ₹", "Pattern",
        "Pattern Confidence", "Pivot ₹", "Distance to Pivot %",
        "Breakout Readiness %", "Decision", "Entry Trigger ₹", "Stop Loss ₹",
        "Target 1 ₹", "Risk:Reward", "RS 1M", "RS 3M", "RS 6M", "RS 12M",
        "RS Leadership", "RSI 14", "MACD Bull Cross", "Above VWAP",
        "20/50/200 MA Trend", "ATR Compression", "BB Squeeze", "ADX 14",
        "Volume Dry-Up", "Volume Expansion Trigger", "Latest Order Catalyst",
        "Order Value ₹ Cr", "Latest Result", "Result Strength",
        "Corporate Catalyst", "Risk Flags", "Why Ranked", "Trigger Needed",
        "Invalidation", "Data Status", "Updated At",
    )

    @staticmethod
    def _ma_trend(technical: dict[str, Any]):
        positions = [technical.get(f"price_vs_sma_{period}") for period in (20, 50, 200)]
        if any(value not in {"ABOVE", "BELOW", "AT"} for value in positions):
            return DATA_UNAVAILABLE
        return " | ".join(
            f"{period}:{position}" for period, position in zip((20, 50, 200), positions)
        )

    @classmethod
    def rows(cls, reports: Iterable[ScanReport], *, projected_at=None) -> list[list[Any]]:
        now = projected_at or timezone.now()
        output: list[list[Any]] = []
        for rank, report in enumerate(_unique_reports(reports), start=1):
            stock = report.snapshot
            technical = dict(_attr(stock, "technical_scanner_fields", {}) or {})
            pivot = _first_present(_attr(stock, "breakout_level"), _attr(stock, "pattern_pivot"))
            target = next((value for value in (_attr(report, "targets", []) or []) if _positive(value) != DATA_UNAVAILABLE), None)
            risk_flags = _join(
                _attr(report, "prebreakout_risk_flags", []),
                _attr(stock, "setup_risk_flags", []),
                _attr(stock, "base_risk_flags", []),
                _attr(stock, "vcp_risk_flags", []),
            )
            mapping = {
                "Rank": rank,
                "Company": _attr(stock, "company_name") or _attr(stock, "symbol") or DATA_UNAVAILABLE,
                "Ticker": _attr(stock, "symbol") or DATA_UNAVAILABLE,
                "Sector": _attr(stock, "sector") or DATA_UNAVAILABLE,
                "Price ₹": _positive(_attr(stock, "last_price")),
                "Pattern": _primary_pattern(stock),
                "Pattern Confidence": _display(_first_present(
                    _attr(stock, "base_quality_score"),
                    _attr(stock, "vcp_quality_score"),
                    _attr(stock, "pivot_quality_score"),
                )),
                "Pivot ₹": _display(pivot),
                "Distance to Pivot %": _display(_attr(stock, "distance_to_breakout_pct")),
                "Breakout Readiness %": _display(_attr(stock, "setup_readiness_score")),
                "Decision": _attr(report, "prebreakout_classification", None) or DATA_UNAVAILABLE,
                "Entry Trigger ₹": _display(pivot),
                "Stop Loss ₹": _positive(_attr(report, "stop_loss")),
                "Target 1 ₹": _positive(target),
                "Risk:Reward": _positive(_attr(report, "risk_reward")),
                "RS 1M": _display(_attr(stock, "rs_1m_pct")),
                "RS 3M": _display(_attr(stock, "rs_3m_pct")),
                "RS 6M": _display(_attr(stock, "rs_6m_pct")),
                "RS 12M": _display(_attr(stock, "rs_12m_pct")),
                "RS Leadership": _attr(stock, "rs_trend_status", None) or DATA_UNAVAILABLE,
                "RSI 14": _display(technical.get("rsi_14")),
                "MACD Bull Cross": _yes_no(technical.get("macd_bullish_cross")),
                "Above VWAP": NOT_SUPPORTED,
                "20/50/200 MA Trend": cls._ma_trend(technical),
                "ATR Compression": _yes_no(technical.get("atr_contracting")),
                "BB Squeeze": _yes_no(_attr(stock, "bollinger_squeeze")),
                "ADX 14": _display(technical.get("adx_14")),
                "Volume Dry-Up": _yes_no(_first_present(
                    _attr(stock, "volume_dry_up_near_pivot"),
                    _attr(stock, "volume_dry_up"),
                )),
                "Volume Expansion Trigger": _yes_no(_attr(stock, "volume_expansion")),
                "Latest Order Catalyst": DATA_UNAVAILABLE,
                "Order Value ₹ Cr": DATA_UNAVAILABLE,
                "Latest Result": DATA_UNAVAILABLE,
                "Result Strength": DATA_UNAVAILABLE,
                "Corporate Catalyst": DATA_UNAVAILABLE,
                "Risk Flags": risk_flags,
                "Why Ranked": _join(_attr(report, "positive_signals", [])),
                "Trigger Needed": _join(_attr(stock, "setup_reason_codes", [])),
                "Invalidation": risk_flags,
                "Data Status": _data_status(stock, now),
                "Updated At": _display(_first_present(_quote_time(stock), _attr(stock, "calculation_timestamp"))),
            }
            row = [mapping[header] for header in cls.HEADERS]
            if len(row) != 40:
                raise ValueError(f"Swing Prebreakout schema mismatch: {len(row)}/40")
            output.append(row)
        return output


@dataclass(frozen=True, slots=True)
class WorkbookScannerReportSet:
    technical_rows: list[list[Any]]
    swing_rows: list[list[Any]]
    projected_at: datetime

    @classmethod
    def build(cls, reports: Iterable[ScanReport], *, projected_at=None):
        now = projected_at or timezone.now()
        report_list = list(reports)
        technical = TechnicalScannerWorkbookProjection.rows(report_list, projected_at=now)
        swing = SwingPrebreakoutProjection.rows(report_list, projected_at=now)
        if not technical or not swing:
            raise EmptyScannerReportSet(
                "Generated scanner report set is empty; existing Sheet rows were preserved."
            )
        return cls(technical_rows=technical, swing_rows=swing, projected_at=now)

    @staticmethod
    def unavailable_count(rows: Sequence[Sequence[Any]]) -> int:
        return sum(value in {DATA_UNAVAILABLE, NOT_SUPPORTED} for row in rows for value in row)

    def freshness(self) -> str:
        index = TechnicalScannerWorkbookProjection.HEADERS.index("Data Status")
        statuses = {row[index] for row in self.technical_rows}
        if "STALE" in statuses:
            return "STALE"
        if statuses and statuses <= {"OK", "PARTIAL"}:
            return "FRESH"
        return DATA_UNAVAILABLE


@dataclass(frozen=True, slots=True)
class WorksheetPublishResult:
    tab: str
    rows: int
    columns: int
    chunks: int


@dataclass(frozen=True, slots=True)
class WorkbookPublishResult:
    technical: WorksheetPublishResult
    swing: WorksheetPublishResult
    duration_ms: int
    run_id: str


class WorkbookScannerPublisher(GoogleSheetBase):
    CHUNK_SIZE = 250
    MAX_RETRIES = 2

    def __init__(self):
        spreadsheet_id = str(
            getattr(settings, "GOOGLE_SHEETS_SPREADSHEET_ID", "")
            or getattr(settings, "GOOGLE_SHEET_ID", "")
        ).strip()
        super().__init__(spreadsheet_id=spreadsheet_id)
        self.technical_tab = str(
            getattr(settings, "GOOGLE_SHEETS_TECHNICAL_TAB", "Technical Scanner")
        )
        self.swing_tab = str(
            getattr(settings, "GOOGLE_SHEETS_SWING_TAB", "Swing Prebreakout")
        )
        # These tabs are intentionally required to exist; never create or rename tabs.
        self.technical_sheet = self.spreadsheet.worksheet(self.technical_tab)
        self.swing_sheet = self.spreadsheet.worksheet(self.swing_tab)

    @staticmethod
    def _column_name(number: int) -> str:
        name = ""
        while number:
            number, remainder = divmod(number - 1, 26)
            name = chr(65 + remainder) + name
        return name

    @staticmethod
    def _transient(exc: BaseException) -> bool:
        if isinstance(exc, (TimeoutError, ConnectionError)):
            return True
        if isinstance(exc, gspread.exceptions.APIError):
            status = getattr(getattr(exc, "response", None), "status_code", None)
            return status == 429 or (isinstance(status, int) and status >= 500)
        return False

    def _retry(self, operation):
        for attempt in range(self.MAX_RETRIES + 1):
            try:
                return operation()
            except Exception as exc:
                if not self._transient(exc) or attempt >= self.MAX_RETRIES:
                    raise
                time.sleep(2**attempt)

    def _verify_header(self, sheet, tab: str, expected: Sequence[str]):
        actual = tuple(self._retry(lambda: sheet.row_values(1)))
        if actual != tuple(expected):
            raise WorksheetHeaderMismatch(
                f"{tab} header contract mismatch: expected {len(expected)} exact columns, "
                f"found {len(actual)}; publishing aborted before writes."
            )

    def _write_rows(self, sheet, tab: str, headers: Sequence[str], rows: list[list[Any]]):
        if not rows:
            raise EmptyScannerReportSet(
                f"{tab} generated zero rows; existing Sheet rows were preserved."
            )
        last_column = self._column_name(len(headers))
        chunks = 0
        for offset in range(0, len(rows), self.CHUNK_SIZE):
            chunk = rows[offset:offset + self.CHUNK_SIZE]
            first_row = offset + 2
            last_row = first_row + len(chunk) - 1
            update = [{
                "range": f"A{first_row}:{last_column}{last_row}",
                "values": chunk,
            }]
            self._retry(lambda update=update: sheet.batch_update(
                update, value_input_option="RAW"
            ))
            chunks += 1
        clear_start = len(rows) + 2
        if sheet.row_count >= clear_start:
            self._retry(lambda: sheet.batch_clear([
                f"A{clear_start}:{last_column}{sheet.row_count}"
            ]))
        return WorksheetPublishResult(
            tab=tab, rows=len(rows), columns=len(headers), chunks=chunks
        )

    def publish(self, report_set: WorkbookScannerReportSet) -> WorkbookPublishResult:
        if not report_set.technical_rows or not report_set.swing_rows:
            raise EmptyScannerReportSet(
                "Generated scanner report set is empty; existing Sheet rows were preserved."
            )
        started = perf_counter()
        run_id = uuid.uuid4().hex[:16]
        # Validate both contracts before either worksheet is mutated.
        self._verify_header(
            self.technical_sheet, self.technical_tab,
            TechnicalScannerWorkbookProjection.HEADERS,
        )
        self._verify_header(
            self.swing_sheet, self.swing_tab, SwingPrebreakoutProjection.HEADERS
        )
        technical = self._write_rows(
            self.technical_sheet, self.technical_tab,
            TechnicalScannerWorkbookProjection.HEADERS, report_set.technical_rows,
        )
        swing = self._write_rows(
            self.swing_sheet, self.swing_tab,
            SwingPrebreakoutProjection.HEADERS, report_set.swing_rows,
        )
        duration_ms = int((perf_counter() - started) * 1000)
        logger.info(
            "workbook_scanner_publish run_id=%s technical_rows=%s swing_rows=%s "
            "freshness=%s duration_ms=%s",
            run_id, technical.rows, swing.rows, report_set.freshness(), duration_ms,
        )
        return WorkbookPublishResult(
            technical=technical, swing=swing, duration_ms=duration_ms, run_id=run_id
        )
