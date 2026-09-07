from __future__ import annotations

from collections import deque
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from django.conf import settings

from apps.companies.models import Company
from apps.dashboard.services.dashboard_service import DashboardService
from apps.market.models import CloudDailyCandle, CloudQuoteSnapshot, MarketOHLC, MarketQuote
from apps.market.services.market_status_service import MarketStatusService
from apps.scanner.models import PreBreakoutSetupOutcome
from apps.scanner.services.scan_report_cache_service import InvalidScanCache, ScanReportCacheService


class StockDetailService:
    """Read-only stock X-ray projection over persisted data and the scanner cache."""

    DEFAULT_RANGE = "12M"
    RANGE_DAYS = {
        "1M": 31,
        "3M": 93,
        "6M": 186,
        "12M": 366,
        "3Y": 1_096,
        "5Y": 1_826,
        "MAX": None,
    }
    IST = ZoneInfo("Asia/Kolkata")
    SUPPORTED_MARKERS = frozenset(
        {
            "PRE-BREAKOUT READY",
            "BREAKOUT ATTEMPT",
            "BREAKOUT CONFIRMED",
            "FAILED ATTEMPT",
            "REPAIRING",
        }
    )

    @classmethod
    def normalize_range(cls, value: str | None) -> str:
        selected = str(value or cls.DEFAULT_RANGE).strip().upper()
        if selected not in cls.RANGE_DAYS:
            raise ValueError(f"Unsupported chart range: {selected}")
        return selected

    @staticmethod
    def _number(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return round(float(value), 4)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _positive_number(value: Any) -> float | None:
        number = StockDetailService._number(value)
        return number if number is not None and number > 0 else None

    @staticmethod
    def _date(value: Any) -> date | None:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if value is None:
            return None
        try:
            return date.fromisoformat(str(value))
        except (TypeError, ValueError):
            return None

    @classmethod
    def company(cls, symbol: str) -> Company:
        return Company.objects.get(symbol__iexact=str(symbol or "").strip())

    @classmethod
    def _quote(cls, company: Company, status_service: MarketStatusService) -> dict[str, Any]:
        if settings.CLOUD_COMPACT_MARKET_DATA:
            quote = (
                CloudQuoteSnapshot.objects.filter(company=company)
                .select_related("company")
                .first()
            )
        else:
            quote = MarketQuote.objects.filter(
                symbol__iexact=company.symbol,
                exchange=company.exchange,
            ).first()

        if quote is None:
            freshness = status_service.for_provider_timestamp(None)
            return {
                "status": freshness.status,
                "freshness": freshness.as_dict(),
                "price": None,
                "change": None,
                "change_percent": None,
                "open": None,
                "high": None,
                "low": None,
                "previous_close": None,
                "volume": None,
                "provider_timestamp": None,
            }

        trade_time = getattr(quote, "last_trade_time", None)
        trade_session = trade_time.astimezone(cls.IST).date() if trade_time else None
        provider_timestamp = getattr(quote, "provider_timestamp", None)
        freshness = status_service.for_provider_timestamp(
            provider_timestamp,
            session=trade_session,
        )
        return {
            "status": freshness.status,
            "freshness": freshness.as_dict(),
            "price": cls._number(quote.last_price),
            "change": cls._number(quote.change),
            "change_percent": cls._number(quote.change_percent),
            "open": cls._number(quote.open_price),
            "high": cls._number(quote.high_price),
            "low": cls._number(quote.low_price),
            "previous_close": cls._number(quote.previous_close),
            "volume": int(quote.volume) if quote.volume is not None else None,
            "provider_timestamp": provider_timestamp.isoformat() if provider_timestamp else None,
        }

    @classmethod
    def _all_candles(cls, company: Company) -> list[dict[str, Any]]:
        if settings.CLOUD_COMPACT_MARKET_DATA:
            rows = CloudDailyCandle.objects.filter(company=company).order_by("session_date").values(
                "session_date", "open", "high", "low", "close", "volume"
            )
            return [
                {
                    "date": row["session_date"],
                    "open": cls._number(row["open"]),
                    "high": cls._number(row["high"]),
                    "low": cls._number(row["low"]),
                    "close": cls._number(row["close"]),
                    "volume": int(row["volume"]),
                }
                for row in rows
            ]

        rows = MarketOHLC.objects.filter(
            symbol__iexact=company.symbol,
            exchange=company.exchange,
            interval=MarketOHLC.Interval.D1,
        ).order_by("candle_time").values(
            "candle_time", "open", "high", "low", "close", "volume"
        )
        return [
            {
                "date": row["candle_time"].astimezone(cls.IST).date(),
                "open": cls._number(row["open"]),
                "high": cls._number(row["high"]),
                "low": cls._number(row["low"]),
                "close": cls._number(row["close"]),
                "volume": int(row["volume"]),
            }
            for row in rows
        ]

    @staticmethod
    def _with_moving_averages(candles: list[dict[str, Any]]) -> list[dict[str, Any]]:
        windows = {50: deque(), 200: deque()}
        totals = {50: 0.0, 200: 0.0}
        enriched: list[dict[str, Any]] = []
        for candle in candles:
            close = float(candle["close"])
            values = dict(candle)
            for period in (50, 200):
                window = windows[period]
                window.append(close)
                totals[period] += close
                if len(window) > period:
                    totals[period] -= window.popleft()
                values[f"ma{period}"] = (
                    round(totals[period] / period, 4)
                    if len(window) == period
                    else None
                )
            enriched.append(values)
        return enriched

    @classmethod
    def _candles(cls, company: Company, range_code: str) -> dict[str, Any]:
        all_candles = cls._with_moving_averages(cls._all_candles(company))
        days = cls.RANGE_DAYS[range_code]
        if all_candles and days is not None:
            cutoff = all_candles[-1]["date"] - timedelta(days=days)
            visible = [candle for candle in all_candles if candle["date"] >= cutoff]
        else:
            visible = all_candles
        serialized = [
            {**candle, "date": candle["date"].isoformat()}
            for candle in visible
        ]
        return {
            "status": "AVAILABLE" if serialized else MarketStatusService.DATA_UNAVAILABLE,
            "range": range_code,
            "interval": "1d",
            "candles": serialized,
            "count": len(serialized),
            "ma50_available": any(candle["ma50"] is not None for candle in visible),
            "ma200_available": any(candle["ma200"] is not None for candle in visible),
            "volume_available": any((candle["volume"] or 0) > 0 for candle in visible),
        }

    @staticmethod
    def _load_report(symbol: str):
        try:
            reports, context = ScanReportCacheService().load_valid()
        except InvalidScanCache:
            return None, {}
        wanted = symbol.upper()
        report = next(
            (item for item in reports if item.snapshot.symbol.upper() == wanted),
            None,
        )
        return report, context

    @classmethod
    def _scanner(cls, report: Any) -> dict[str, Any]:
        if report is None:
            return {
                "status": MarketStatusService.DATA_UNAVAILABLE,
                "lifecycle": MarketStatusService.DATA_UNAVAILABLE,
                "metrics": {},
                "levels": {},
                "positive_evidence": [],
                "risk_flags": [],
                "quality_flags": [],
                "strategies": [],
            }

        stock = report.snapshot
        distance_52w = None
        if stock.week_52_high and stock.week_52_high > 0:
            distance_52w = round(
                ((stock.week_52_high - stock.last_price) / stock.week_52_high) * 100,
                2,
            )
        entry_zone = report.entry_zone
        entry_low = report.entry_low if report.entry_low is not None else (
            entry_zone[0] if entry_zone else None
        )
        entry_high = report.entry_high if report.entry_high is not None else (
            entry_zone[1] if entry_zone else None
        )
        pivot = cls._positive_number(stock.breakout_level) or cls._positive_number(report.resistance)
        quality_flags = list(dict.fromkeys(
            [*report.prebreakout_data_quality, *stock.data_quality_reason_codes]
        ))
        return {
            "status": "AVAILABLE",
            "lifecycle": DashboardService._setup_state(report),
            "engine_classification": report.prebreakout_classification or None,
            "scanner_session": cls._date(stock.latest_daily_session),
            "metrics": {
                "rs_rating": stock.rs_rating,
                "distance_from_pivot_percent": cls._number(
                    stock.distance_to_breakout_pct
                    if stock.distance_to_breakout_pct is not None
                    else report.distance_from_breakout
                ),
                "atr_tightening": stock.atr_contracting,
                "atr_contraction_ratio": cls._number(stock.atr_contraction_ratio),
                "volume_dry_up": stock.volume_dry_up,
                "up_down_volume_ratio": cls._number(stock.up_down_volume_ratio),
                "accumulation_distribution_balance": cls._number(
                    stock.accumulation_distribution_balance
                ),
                "distance_from_52w_high_percent": distance_52w,
                "quantum_score": report.overall_score,
                "prebreakout_score": report.prebreakout_score,
                "breakout_probability": cls._number(report.breakout_probability),
                "risk_reward": cls._number(report.risk_reward),
                "liquidity_score": cls._positive_number(stock.liquidity_score),
                "data_quality_state": stock.data_quality_state or None,
                "base_duration_sessions": stock.base_duration_sessions,
                "base_depth_percent": cls._number(stock.base_depth_pct),
            },
            "levels": {
                "pivot": pivot,
                "resistance": cls._positive_number(report.resistance),
                "support": cls._positive_number(report.support),
                "base_high": cls._positive_number(stock.base_high),
                "base_low": cls._positive_number(stock.base_low),
                "breakout_level": cls._positive_number(stock.breakout_level) or pivot,
                "entry_low": cls._positive_number(entry_low),
                "entry_high": cls._positive_number(entry_high),
                "stop_loss": cls._positive_number(report.stop_loss),
                "targets": [
                    target for value in report.targets
                    if (target := cls._positive_number(value)) is not None
                ],
            },
            "positive_evidence": list(dict.fromkeys(
                [*report.positive_signals, *stock.setup_reason_codes]
            )),
            "risk_flags": list(dict.fromkeys(
                [
                    *report.prebreakout_risk_flags,
                    *stock.setup_risk_flags,
                    *stock.failed_breakout_risk_flags,
                ]
            )),
            "quality_flags": quality_flags,
            "strategies": [
                {
                    "name": strategy.strategy_name,
                    "score": strategy.score,
                    "passed": strategy.passed,
                }
                for strategy in sorted(
                    report.strategies,
                    key=lambda item: (item.score, item.weight),
                    reverse=True,
                )
            ],
        }

    @classmethod
    def _markers(cls, company: Company, scanner: dict[str, Any]) -> list[dict[str, Any]]:
        markers: list[dict[str, Any]] = []
        for outcome in PreBreakoutSetupOutcome.objects.filter(
            symbol__iexact=company.symbol,
            exchange=company.exchange,
        ).order_by("evaluation_session").values(
            "evaluation_session",
            "breakout_occurred",
            "breakout_session",
            "failed_breakout",
            "evaluated_through_session",
            "classification",
            "feature_snapshot",
        ):
            state = None
            session = outcome["evaluation_session"]
            if outcome["failed_breakout"] is True:
                state = "FAILED ATTEMPT"
                session = outcome["evaluated_through_session"] or outcome["breakout_session"] or session
            elif outcome["breakout_occurred"] is True and outcome["breakout_session"]:
                state = "BREAKOUT CONFIRMED"
                session = outcome["breakout_session"]
            else:
                snapshot = outcome["feature_snapshot"] or {}
                candidate = str(
                    snapshot.get("setup_lifecycle") or outcome["classification"] or ""
                ).replace("_", " ").upper()
                if candidate in cls.SUPPORTED_MARKERS:
                    state = candidate
            if state:
                markers.append({"date": session.isoformat(), "state": state})

        current_state = scanner.get("lifecycle")
        current_session = cls._date(scanner.get("scanner_session"))
        if current_state in cls.SUPPORTED_MARKERS and current_session:
            markers.append({"date": current_session.isoformat(), "state": current_state})

        return list({(item["date"], item["state"]): item for item in markers}.values())

    @classmethod
    def detail(
        cls,
        symbol: str,
        *,
        range_code: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        selected_range = cls.normalize_range(range_code)
        company = cls.company(symbol)
        status_service = MarketStatusService(now=now)
        report, _context = cls._load_report(company.symbol)
        scanner = cls._scanner(report)
        return {
            "company": {
                "name": company.name,
                "symbol": company.symbol,
                "exchange": company.exchange,
                "sector": company.sector or None,
                "industry": company.industry or None,
                "instrument_key": company.upstox_instrument_key or None,
            },
            "quote": cls._quote(company, status_service),
            "scanner": scanner,
            "chart": cls._candles(company, selected_range),
            "markers": cls._markers(company, scanner),
            "ranges": list(cls.RANGE_DAYS),
        }
