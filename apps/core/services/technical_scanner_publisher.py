from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from time import perf_counter
from typing import Any, Iterable

import gspread
from django.conf import settings
from django.utils import timezone

from apps.core.services.google_sheet_base import GoogleSheetBase
from apps.scanner.engine.decision_engine import ScanReport

logger = logging.getLogger(__name__)
UNAVAILABLE = "DATA_UNAVAILABLE"
NOT_SUPPORTED = "NOT_SUPPORTED"


@dataclass(frozen=True, slots=True)
class TechnicalScannerPublishResult:
    rows: int
    columns: int
    chunks: int
    duration_ms: int
    published_at: datetime
    run_id: str


class TechnicalScannerProjectionBuilder:
    HEADERS = [
        "Company", "Ticker", "Sector", "Industry", "Last Price",
        "Price Timestamp", "Latest Completed Daily Session", "Last Scanner Update",
        "Data Age Sec", "Data Status", "Structural Session", "Quote Timestamp",
        "Scanner Calculated At", "Sheet Published At", "Is Stale",
        "SMA 20", "Price vs SMA20", "SMA20 Bullish Cross",
        "EMA 20", "Price vs EMA20", "EMA20 Bullish Cross",
        "SMA 50", "Price vs SMA50", "SMA50 Bullish Cross",
        "EMA 50", "Price vs EMA50", "EMA50 Bullish Cross",
        "SMA 100", "Price vs SMA100", "SMA100 Bullish Cross",
        "EMA 100", "Price vs EMA100", "EMA100 Bullish Cross",
        "SMA 200", "Price vs SMA200", "SMA200 Bullish Cross",
        "EMA 200", "Price vs EMA200", "EMA200 Bullish Cross",
        "VWAP", "Price vs VWAP", "VWAP Reclaim", "VWAP Breakdown",
        "Last Committed Bar Close", "Last Committed Bar Timestamp",
        "RSI 5", "RSI 9", "RSI 14", "RSI 21", "RSI14 State",
        "RS 1M", "RS 3M", "RS 6M", "RS 12M", "RS Acceleration",
        "RS Leadership State", "RS Benchmark",
        "MACD", "MACD Signal", "MACD Histogram", "MACD Bullish Cross",
        "MACD Bearish Cross", "BB Upper", "BB Middle", "BB Lower",
        "BB Width %", "Bollinger Squeeze", "Price Position in BB",
        "ATR 14", "ATR %", "ATR Contracting", "ATR Expansion",
        "ADX 14", "+DI", "-DI", "ADX State",
        "VCP", "Flat Base", "Cup & Handle", "Double Bottom",
        "Ascending Triangle", "Bull Flag", "Darvas Box", "Head & Shoulders",
        "Pattern Count", "Primary Pattern", "Pattern Confidence", "Pattern Stage",
        "Pattern Pivot", "Distance to Pivot %", "Pattern Invalidation",
        "Rank", "Trend Score", "Momentum Score", "Volatility Compression Score",
        "Pattern Score", "RS Score", "Technical Score", "Readiness",
        "Decision State", "Why Ranked", "Top Positive Evidence", "Top Risk",
        "Trigger Needed", "Invalidation", "Market State", "Tradeability",
    ]

    @staticmethod
    def _attr(obj: Any, name: str, default=None):
        return getattr(obj, name, default)

    @staticmethod
    def _display(value: Any, unavailable: str = UNAVAILABLE):
        if value is None or value == "":
            return unavailable
        if isinstance(value, datetime) or hasattr(value, "isoformat"):
            return value.isoformat()
        return value

    @staticmethod
    def _yes_no(value: Any):
        return UNAVAILABLE if value is None else "YES" if value is True else "NO"

    @staticmethod
    def _detected(value: Any):
        return UNAVAILABLE if value is None else "DETECTED" if value is True else "NOT_DETECTED"

    @classmethod
    def _family(cls, report: ScanReport, *names: str):
        families = cls._attr(report, "evidence_family_scores", None) or report.component_scores or {}
        for name in names:
            item = families.get(name) or families.get(name.upper()) or families.get(name.title())
            if isinstance(item, dict):
                value = item.get("score", item.get("value"))
            else:
                value = item
            if value is not None:
                return value
        return UNAVAILABLE

    @staticmethod
    def _rsi_state(value):
        if value is None:
            return UNAVAILABLE
        if value < 30:
            return "Oversold"
        if value < 45:
            return "Weak"
        if value < 60:
            return "Neutral"
        if value < 70:
            return "Strong"
        return "Overbought"

    @staticmethod
    def _adx_state(value):
        if value is None:
            return UNAVAILABLE
        if value < 15:
            return "Weak"
        if value < 20:
            return "Developing"
        if value < 25:
            return "Moderate"
        if value <= 40:
            return "Strong"
        return "Very Strong"

    @classmethod
    def _quote_time(cls, stock):
        return (
            cls._attr(stock, "quote_timestamp")
            or cls._attr(stock, "provider_timestamp")
            or cls._attr(stock, "last_trade_timestamp")
        )

    @classmethod
    def _age(cls, stock, now):
        supplied = cls._attr(stock, "data_age_seconds")
        if supplied is not None:
            return max(0.0, float(supplied))
        quote_time = cls._quote_time(stock)
        if not isinstance(quote_time, datetime):
            return None
        if timezone.is_naive(quote_time):
            quote_time = timezone.make_aware(quote_time)
        return max(0.0, (now - quote_time).total_seconds())

    @classmethod
    def _data_status(cls, stock, now):
        quality = str(cls._attr(stock, "data_quality_state", "")).upper()
        age = cls._age(stock, now)
        stale_after = int(getattr(settings, "TECHNICAL_SCANNER_STALE_AFTER_SECONDS", 300))
        stale = quality in {"STALE", "INVALID"} or age is None or age > stale_after
        if quality == "INVALID":
            return "DATA_UNAVAILABLE", stale
        if stale:
            return "STALE", True
        if quality == "PARTIAL":
            return "PARTIAL", False
        if quality == "FRESH":
            return "OK", False
        return UNAVAILABLE, stale

    @classmethod
    def _patterns(cls, stock):
        values = {
            "VCP": cls._attr(stock, "vcp_detected"),
            "Flat Base": cls._attr(stock, "flat_base"),
            "Cup & Handle": NOT_SUPPORTED,
            "Double Bottom": NOT_SUPPORTED,
            "Ascending Triangle": cls._attr(stock, "ascending_triangle"),
            "Bull Flag": NOT_SUPPORTED,
            "Darvas Box": cls._attr(stock, "darvas_consolidation"),
            "Head & Shoulders": NOT_SUPPORTED,
        }
        detected = [name for name, value in values.items() if value is True]
        return values, detected

    @staticmethod
    def _join(values):
        return " | ".join(str(value) for value in (values or []) if value) or UNAVAILABLE

    @classmethod
    def rows(cls, reports: Iterable[ScanReport], published_at=None) -> list[list[Any]]:
        now = published_at or timezone.now()
        unique = {}
        authoritative_rank = {}
        for rank, report in enumerate(reports, start=1):
            key = (
                str(report.snapshot.exchange).upper(),
                str(report.snapshot.symbol).upper(),
            )
            if key not in unique:
                unique[key] = report
                authoritative_rank[key] = rank

        output = []
        for key in sorted(unique):
            report = unique[key]
            stock = report.snapshot
            tech = dict(cls._attr(stock, "technical_scanner_fields", {}) or {})
            patterns, detected_patterns = cls._patterns(stock)
            status, stale = cls._data_status(stock, now)
            age = cls._age(stock, now)
            quote_time = cls._quote_time(stock)
            scanner_time = cls._attr(stock, "calculation_timestamp") or cls._attr(stock, "timestamp")
            structural_session = cls._attr(stock, "latest_daily_session")
            # Base 28b has no legitimate current-session intraday VWAP source.
            live_vwap = cls._attr(stock, "live_vwap")
            last_price = cls._attr(stock, "last_price")
            price_vs_vwap = (
                UNAVAILABLE if live_vwap is None or last_price is None
                else "ABOVE" if last_price > live_vwap
                else "BELOW" if last_price < live_vwap else "AT"
            )
            row = [
                cls._attr(stock, "company_name") or cls._attr(stock, "symbol"),
                cls._attr(stock, "symbol"), cls._attr(stock, "sector") or UNAVAILABLE,
                cls._attr(stock, "industry") or UNAVAILABLE,
                UNAVAILABLE if last_price is None or float(last_price) <= 0 else last_price,
                cls._display(quote_time), cls._display(structural_session),
                cls._display(scanner_time), cls._display(age), status,
                cls._display(structural_session), cls._display(quote_time),
                cls._display(scanner_time), now.isoformat(), cls._yes_no(stale),
            ]
            for period in (20, 50, 100, 200):
                for kind in ("sma", "ema"):
                    name = f"{kind}_{period}"
                    row.extend([
                        cls._display(tech.get(name)),
                        tech.get(f"price_vs_{name}", UNAVAILABLE),
                        cls._yes_no(tech.get(f"{name}_bullish_cross")),
                    ])
            row.extend([
                cls._display(live_vwap), price_vs_vwap,
                cls._yes_no(tech.get("vwap_reclaim")),
                cls._yes_no(tech.get("vwap_breakdown")),
                cls._display(tech.get("last_committed_bar_close")),
                cls._display(tech.get("last_committed_bar_timestamp")),
                cls._display(tech.get("rsi_5")), cls._display(tech.get("rsi_9")),
                cls._display(tech.get("rsi_14")), cls._display(tech.get("rsi_21")),
                cls._rsi_state(tech.get("rsi_14")),
                cls._display(cls._attr(stock, "rs_1m_pct")),
                cls._display(cls._attr(stock, "rs_3m_pct")),
                cls._display(cls._attr(stock, "rs_6m_pct")),
                cls._display(cls._attr(stock, "rs_12m_pct")),
                cls._display(cls._attr(stock, "rs_acceleration")),
                cls._attr(stock, "rs_leadership_state")
                or cls._attr(stock, "rs_trend_status") or UNAVAILABLE,
                cls._attr(stock, "rs_benchmark_name", "NIFTY 50") or "NIFTY 50",
                cls._display(tech.get("macd")), cls._display(tech.get("macd_signal")),
                cls._display(tech.get("macd_histogram")),
                cls._yes_no(tech.get("macd_bullish_cross")),
                cls._yes_no(tech.get("macd_bearish_cross")),
                cls._display(tech.get("bb_upper")), cls._display(tech.get("bb_middle")),
                cls._display(tech.get("bb_lower")), cls._display(tech.get("bb_width_pct")),
                cls._yes_no(cls._attr(stock, "bollinger_squeeze")),
                cls._display(tech.get("price_position_in_bb")),
                cls._display(tech.get("atr_14")), cls._display(tech.get("atr_pct")),
                cls._yes_no(tech.get("atr_contracting")),
                cls._yes_no(tech.get("atr_expansion")),
                cls._display(tech.get("adx_14")), cls._display(tech.get("plus_di")),
                cls._display(tech.get("minus_di")), cls._adx_state(tech.get("adx_14")),
                cls._detected(patterns["VCP"]), cls._detected(patterns["Flat Base"]),
                patterns["Cup & Handle"], patterns["Double Bottom"],
                cls._detected(patterns["Ascending Triangle"]), patterns["Bull Flag"],
                cls._detected(patterns["Darvas Box"]), patterns["Head & Shoulders"],
                len(detected_patterns), detected_patterns[0] if detected_patterns else UNAVAILABLE,
                cls._display(
                    cls._attr(stock, "pattern_quality")
                    or cls._attr(stock, "vcp_quality_score")
                    or cls._attr(stock, "base_quality_score")
                ),
                cls._attr(stock, "setup_lifecycle") or UNAVAILABLE,
                cls._display(
                    cls._attr(stock, "pattern_pivot")
                    or cls._attr(stock, "breakout_level")
                ),
                cls._display(cls._attr(stock, "distance_to_breakout_pct")),
                cls._join(
                    cls._attr(stock, "pattern_invalidity_reasons")
                    or cls._attr(stock, "setup_risk_flags")
                ),
                authoritative_rank[key], cls._family(report, "trend", "trend_structure"),
                cls._family(report, "momentum"),
                cls._family(report, "volatility", "compression"),
                cls._family(report, "pattern", "base"),
                cls._display(
                    cls._attr(stock, "rs_rating") or cls._attr(stock, "rs_composite_score")
                ),
                cls._attr(report, "overall_rank_score", report.overall_score),
                cls._attr(report, "readiness_score", cls._attr(stock, "setup_readiness_score")),
                cls._attr(report, "final_decision", report.prebreakout_classification)
                or UNAVAILABLE,
                cls._attr(report, "decision_reason") or report.prebreakout_classification
                or UNAVAILABLE,
                cls._join(
                    cls._attr(report, "top_positive_reasons") or report.positive_signals
                ),
                cls._join(
                    cls._attr(report, "top_risk_reasons") or report.prebreakout_risk_flags
                ),
                cls._join(cls._attr(stock, "setup_reason_codes")),
                cls._join(cls._attr(stock, "setup_risk_flags")),
                cls._attr(stock, "market_regime") or UNAVAILABLE,
                cls._attr(stock, "tradeability_state") or UNAVAILABLE,
            ])
            if len(row) != len(cls.HEADERS):
                raise ValueError(
                    f"Technical Scanner schema mismatch: {len(row)}/{len(cls.HEADERS)}"
                )
            output.append(row)
        return output


class TechnicalScannerPublisher(GoogleSheetBase):
    CHUNK_SIZE = 500
    MAX_RETRIES = 2

    def __init__(self):
        spreadsheet_id = str(
            getattr(settings, "GOOGLE_SHEETS_SPREADSHEET_ID", "")
            or getattr(settings, "GOOGLE_SHEET_ID", "")
        ).strip()
        super().__init__(spreadsheet_id=spreadsheet_id)
        self.tab_name = str(
            getattr(settings, "GOOGLE_SHEETS_TECHNICAL_TAB", "Technical Scanner")
        )
        self.sheet = self.worksheet(
            self.tab_name, rows=5_000,
            cols=len(TechnicalScannerProjectionBuilder.HEADERS),
        )

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
                time.sleep(2 ** attempt)

    def publish(self, reports: Iterable[ScanReport]) -> TechnicalScannerPublishResult:
        started = perf_counter()
        run_id = uuid.uuid4().hex[:16]
        published_at = timezone.now()
        rows = TechnicalScannerProjectionBuilder.rows(reports, published_at)
        values = [TechnicalScannerProjectionBuilder.HEADERS, *rows]
        last_column = self._column_name(len(TechnicalScannerProjectionBuilder.HEADERS))
        updates = []
        for start in range(0, len(values), self.CHUNK_SIZE):
            chunk = values[start:start + self.CHUNK_SIZE]
            first_row = start + 1
            last_row = first_row + len(chunk) - 1
            updates.append({
                "range": f"A{first_row}:{last_column}{last_row}",
                "values": chunk,
            })
        self._retry(lambda: self.sheet.batch_update(updates, value_input_option="RAW"))
        clear_start = len(values) + 1
        if self.sheet.row_count >= clear_start:
            self._retry(lambda: self.sheet.batch_clear([
                f"A{clear_start}:{last_column}{self.sheet.row_count}"
            ]))
        duration_ms = int((perf_counter() - started) * 1000)
        logger.info(
            "technical_sheet_publish run_id=%s symbols_total=%s symbols_processed=%s "
            "symbols_failed=0 sheet_rows_updated=%s sheet_publish_duration_ms=%s "
            "stale_count=%s unavailable_count=%s last_successful_publish_at=%s",
            run_id, len(rows), len(rows), len(rows), duration_ms,
            sum(row[9] == "STALE" for row in rows),
            sum(row[9] == UNAVAILABLE for row in rows), published_at.isoformat(),
        )
        return TechnicalScannerPublishResult(
            rows=len(rows), columns=len(TechnicalScannerProjectionBuilder.HEADERS),
            chunks=len(updates), duration_ms=duration_ms,
            published_at=published_at, run_id=run_id,
        )
