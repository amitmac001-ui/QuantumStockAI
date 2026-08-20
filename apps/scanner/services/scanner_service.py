from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Iterable, Mapping
from math import isfinite
from typing import Any

import pandas as pd
from django.conf import settings
from django.utils import timezone

from apps.companies.models import Company
from apps.market.indicators.engine import indicator_engine
from apps.market.models import CloudDailyCandle, CloudQuoteSnapshot, MarketOHLC, MarketQuote
from apps.market.services.benchmark_history_service import BenchmarkHistoryService
from apps.market.services.daily_history_sync_service import DailyHistorySyncService
from apps.scanner.engine.base_quality_features import base_quality_feature_extractor
from apps.scanner.engine.failed_breakout_features import failed_breakout_feature_extractor
from apps.scanner.engine.overhead_supply_features import overhead_supply_feature_extractor
from apps.scanner.engine.setup_lifecycle_features import setup_lifecycle_feature_extractor
from apps.scanner.engine.supply_demand_features import supply_demand_feature_extractor
from apps.scanner.engine.technical_scanner_features import (
    technical_scanner_feature_extractor,
)
from apps.scanner.engine.data_quality_features import data_quality_gate_v2
from apps.scanner.engine.decision_engine import ScanReport, scanner_engine
from apps.scanner.engine.market_context_features import (
    market_context_feature_extractor,
)
from apps.scanner.engine.price_structure_features import (
    price_structure_feature_extractor,
)
from apps.scanner.engine.pivot_features import pivot_feature_extractor
from apps.scanner.engine.prebreakout_config import (
    RS_ALIGNMENT_BUFFER_OBSERVATIONS,
    RS_BENCHMARK_LOAD_OBSERVATIONS,
)
from apps.scanner.engine.relative_strength_features import (
    assign_rs_ratings,
    relative_strength_feature_extractor,
)
from apps.scanner.engine.trend_momentum_features import (
    trend_momentum_feature_extractor,
)
from apps.scanner.engine.volatility_features import volatility_feature_extractor
from apps.scanner.engine.volume_features import volume_feature_extractor
from apps.scanner.engine.weekly_features import weekly_feature_extractor
from apps.scanner.engine.vcp_features import vcp_feature_extractor
from apps.scanner.repositories.scanner_repository import ScannerRepository

logger = logging.getLogger(__name__)


class ScannerService:
    """Builds deterministic live-market scan reports from persisted market data."""

    DEFAULT_LIMIT = 100
    HISTORY_WINDOW = 252
    VOLUME_WINDOW = 20
    CONSOLIDATION_LOOKBACK = 45
    RESISTANCE_LOOKBACK = 60
    CONSOLIDATION_RANGE_PERCENT = 12.0
    RESISTANCE_TOLERANCE_PERCENT = 1.5
    MIN_TOUCH_SEPARATION = 3

    @staticmethod
    def _key(symbol: str, exchange: str) -> tuple[str, str]:
        return (
            str(symbol or "").strip().upper(),
            str(exchange or "NSE").strip().upper(),
        )

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            if value is None:
                return default
            numeric_value = float(value)
        except (TypeError, ValueError):
            return default

        return numeric_value if isfinite(numeric_value) else default

    @classmethod
    def _safe_int(cls, value: Any, default: int = 0) -> int:
        return int(cls._safe_float(value, float(default)))

    @classmethod
    def _load_company_map(cls) -> dict[tuple[str, str], Company]:
        companies: dict[tuple[str, str], Company] = {}
        queryset = Company.objects.filter(
            is_active=True,
            instrument_status=Company.InstrumentStatus.ACTIVE,
        ).only(
            "symbol",
            "exchange",
            "name",
            "sector",
            "industry",
            "market_cap",
        )

        for company in queryset.iterator(chunk_size=2_000):
            key = cls._key(company.symbol, company.exchange)
            if key[0]:
                companies[key] = company

        return companies

    @classmethod
    def _load_quote_map(cls) -> dict[tuple[str, str], MarketQuote]:
        quotes: dict[tuple[str, str], MarketQuote] = {}
        if settings.CLOUD_COMPACT_MARKET_DATA:
            queryset = CloudQuoteSnapshot.objects.select_related("company").only(
                "company__symbol", "company__exchange", "company__name",
                "last_price", "open_price", "high_price", "low_price",
                "previous_close", "change", "change_percent", "volume",
                "last_trade_time", "provider_timestamp", "updated_at",
            )
        else:
            queryset = MarketQuote.objects.all().only(
                "symbol", "exchange", "company_name", "last_price", "open_price",
                "high_price", "low_price", "previous_close", "change",
                "change_percent", "volume", "last_trade_time",
                "provider_timestamp", "updated_at",
            )
        for quote in queryset.iterator(chunk_size=5_000):
            key = cls._key(quote.symbol, quote.exchange)
            if key[0]:
                quotes[key] = quote
        return quotes
    @classmethod
    def _load_daily_candles(
        cls, history_window: int | None = None
    ) -> dict[tuple[str, str], list[MarketOHLC]]:
        candles_by_instrument: dict[tuple[str, str], list[MarketOHLC]] = defaultdict(list)
        maximum_history = history_window or (
            cls.HISTORY_WINDOW + RS_ALIGNMENT_BUFFER_OBSERVATIONS
        )
        if settings.CLOUD_COMPACT_MARKET_DATA:
            queryset = (
                CloudDailyCandle.objects.select_related("company")
                .only(
                    "company__symbol", "company__exchange", "session_date",
                    "open", "high", "low", "close", "volume",
                    "provider_timestamp", "data_quality_flags",
                ).order_by("company_id", "-session_date")
            )
        else:
            queryset = (
                MarketOHLC.objects.filter(interval=MarketOHLC.Interval.D1)
                .only(
                    "symbol", "exchange", "open", "high", "low", "close", "volume",
                    "candle_time", "provider_timestamp", "data_quality_flags",
                ).order_by("exchange", "symbol", "-candle_time")
            )
        for candle in queryset.iterator(chunk_size=5_000):
            key = cls._key(candle.symbol, candle.exchange)
            bucket = candles_by_instrument[key]
            if key[0] and len(bucket) < maximum_history:
                bucket.append(candle)
        return candles_by_instrument
    @classmethod
    def _average(cls, values: Iterable[int | float]) -> float:
        valid_values = [float(value) for value in values if value is not None]
        return sum(valid_values) / len(valid_values) if valid_values else 0.0

    @classmethod
    def _indicator_frame(cls, candles: list[MarketOHLC]) -> tuple[pd.DataFrame, Mapping[str, Any]]:
        if not candles:
            return pd.DataFrame(), {}

        frame = pd.DataFrame(
            {
                "open": [cls._safe_float(candle.open) for candle in reversed(candles)],
                "high": [cls._safe_float(candle.high) for candle in reversed(candles)],
                "low": [cls._safe_float(candle.low) for candle in reversed(candles)],
                "close": [cls._safe_float(candle.close) for candle in reversed(candles)],
                "volume": [cls._safe_int(candle.volume) for candle in reversed(candles)],
                "timestamp": [candle.candle_time for candle in reversed(candles)],
                "provider_quality_flags": [
                    candle.data_quality_flags or [] for candle in reversed(candles)
                ],
            }
        )

        if frame.empty:
            return frame, {}

        enriched_frame = indicator_engine.calculate(frame)
        return enriched_frame, enriched_frame.iloc[-1]

    @classmethod
    def _consolidation_days(cls, candles: list[MarketOHLC]) -> int:
        if len(candles) < 10:
            return 0

        highest_high = 0.0
        lowest_low: float | None = None
        days = 0

        for candle in candles[: cls.CONSOLIDATION_LOOKBACK]:
            high = cls._safe_float(candle.high)
            low = cls._safe_float(candle.low)
            if high <= 0 or low <= 0:
                break

            highest_high = max(highest_high, high)
            lowest_low = low if lowest_low is None else min(lowest_low, low)

            if lowest_low <= 0:
                break

            price_range = ((highest_high - lowest_low) / lowest_low) * 100.0
            if price_range > cls.CONSOLIDATION_RANGE_PERCENT:
                break

            days += 1

        return days

    @classmethod
    def _resistance_tests(cls, candles: list[MarketOHLC], resistance: float) -> int:
        if resistance <= 0:
            return 0

        touches = 0
        last_touch_index: int | None = None

        for index, candle in enumerate(candles[: cls.RESISTANCE_LOOKBACK]):
            high = cls._safe_float(candle.high)
            distance = abs(high - resistance) / resistance * 100.0
            if distance > cls.RESISTANCE_TOLERANCE_PERCENT:
                continue

            if last_touch_index is None or index - last_touch_index >= cls.MIN_TOUCH_SEPARATION:
                touches += 1
                last_touch_index = index

        return touches

    @classmethod
    def _build_snapshot(
        cls,
        company: Company | None,
        quote: MarketQuote,
        candles: list[MarketOHLC],
        benchmark_frame: pd.DataFrame,
        market_context_mapping: Mapping[str, Any],
        evaluation_time=None,
    ) -> dict[str, Any]:
        enriched_frame, latest = cls._indicator_frame(candles)
        technical_scanner_fields = technical_scanner_feature_extractor.extract(
            enriched_frame
        )
        market_data_timestamp = quote.last_trade_time
        latest_completed_session = (
            DailyHistorySyncService.session_date(benchmark_frame["timestamp"].iloc[-1])
            if not benchmark_frame.empty and "timestamp" in benchmark_frame
            else None
        )
        quality_features = data_quality_gate_v2.evaluate(
            enriched_frame, benchmark_frame, latest_completed_session
        )
        weekly_features = weekly_feature_extractor.extract(enriched_frame)
        trend_momentum = trend_momentum_feature_extractor.extract(
            enriched_frame,
            market_data_timestamp=market_data_timestamp,
            now=evaluation_time,
            latest_completed_session=latest_completed_session,
        )
        volatility = volatility_feature_extractor.extract(enriched_frame)
        volume_features = volume_feature_extractor.extract(enriched_frame)
        price_structure = price_structure_feature_extractor.extract(enriched_frame)
        pivot_features = pivot_feature_extractor.extract(
            enriched_frame,
            current_price=cls._safe_float(quote.last_price),
            price_structure=price_structure,
        )
        vcp_features = vcp_feature_extractor.extract(
            enriched_frame,
            volatility=volatility,
            volume=volume_features,
            price_structure=price_structure,
            pivot=pivot_features,
        )
        base_quality_features = base_quality_feature_extractor.extract(
            enriched_frame,
            pivot=pivot_features,
            structure=price_structure,
            vcp=vcp_features,
        )
        relative_strength_features = relative_strength_feature_extractor.extract(
            enriched_frame,
            benchmark_frame,
        )
        volume_features.volume_dry_up_near_pivot = bool(
            volume_features.volume_dry_up is True and pivot_features.near_pivot is True
        )
        if volume_features.volume_dry_up_near_pivot:
            volume_features.volume_reason_codes.append("VOLUME_DRY_UP_NEAR_PIVOT")
        supply_demand_features = supply_demand_feature_extractor.extract(
            enriched_frame, pivot=pivot_features, volume=volume_features
        )
        overhead_supply_features = overhead_supply_feature_extractor.extract(
            enriched_frame,
            pivot=pivot_features,
            current_price=cls._safe_float(quote.last_price),
        )
        failed_breakout_features = failed_breakout_feature_extractor.extract(
            enriched_frame, pivot=pivot_features
        )
        setup_lifecycle_features = setup_lifecycle_feature_extractor.extract(
            last_price=cls._safe_float(quote.last_price),
            quality=quality_features,
            trend=trend_momentum,
            volatility=volatility,
            volume=volume_features,
            structure=price_structure,
            pivot=pivot_features,
            vcp=vcp_features,
            base=base_quality_features,
            relative_strength=relative_strength_features,
            weekly=weekly_features,
            supply_demand=supply_demand_features,
            overhead_supply=overhead_supply_features,
            failed_breakout=failed_breakout_features,
        )
        quality_mapping = quality_features.as_mapping()
        weekly_mapping = weekly_features.as_mapping()
        base_quality_mapping = base_quality_features.as_mapping()
        trend_mapping = trend_momentum.as_mapping()
        volatility_mapping = volatility.as_mapping()
        volume_mapping = volume_features.as_mapping()
        price_structure_mapping = price_structure.as_mapping()
        pivot_mapping = pivot_features.as_mapping()
        vcp_mapping = vcp_features.as_mapping()
        relative_strength_mapping = relative_strength_features.as_mapping()
        supply_demand_mapping = supply_demand_features.as_mapping()
        overhead_supply_mapping = overhead_supply_features.as_mapping()
        failed_breakout_mapping = failed_breakout_features.as_mapping()
        setup_lifecycle_mapping = setup_lifecycle_features.as_mapping()
        data_quality = list(
            dict.fromkeys(
                [
                    *trend_mapping.pop("data_quality"),
                    *volatility_mapping.pop("data_quality"),
                    *volume_mapping.pop("data_quality"),
                    *price_structure_mapping.pop("data_quality"),
                    *pivot_mapping.pop("data_quality"),
                    *relative_strength_mapping.pop("data_quality"),
                    *weekly_mapping.pop("weekly_data_quality"),
                    *quality_mapping["data_quality_reason_codes"],
                ]
            )
        )
        latest_candle_time = candles[0].candle_time if candles else None
        if latest_completed_session is not None and not DailyHistorySyncService.is_fresh(
            latest_candle_time, latest_completed_session
        ):
            data_quality = list(
                dict.fromkeys([*data_quality, "STALE_DAILY_HISTORY", "STALE_MARKET_DATA"])
            )
        if quote.last_trade_time is None:
            data_quality = list(
                dict.fromkeys([*data_quality, "MISSING_LAST_TRADE_TIME", "STALE_MARKET_DATA"])
            )

        week_52_candles = candles[: cls.HISTORY_WINDOW]
        highs = [cls._safe_float(candle.high) for candle in week_52_candles]
        lows = [cls._safe_float(candle.low) for candle in week_52_candles]
        volumes = [cls._safe_int(candle.volume) for candle in candles]

        last_price = cls._safe_float(quote.last_price)
        previous_close = cls._safe_float(quote.previous_close)
        high_price = cls._safe_float(quote.high_price)
        low_price = cls._safe_float(quote.low_price)
        week_52_high = max(highs) if highs else max(last_price, high_price)
        week_52_low = min(lows) if lows else min(
            value for value in (last_price, low_price) if value > 0
        ) if any(value > 0 for value in (last_price, low_price)) else 0.0
        average_volume = cls._average(volumes[: cls.VOLUME_WINDOW])

        if week_52_high > week_52_low > 0:
            relative_strength = 50.0 + ((last_price - week_52_low) / (week_52_high - week_52_low) * 50.0)
        else:
            relative_strength = 0.0

        company_name = str(quote.company_name or quote.symbol).strip()
        sector = ""
        industry = ""
        market_cap = 0.0
        if company is not None:
            company_name = str(company.name or company_name).strip()
            sector = str(company.sector or "").strip()
            industry = str(company.industry or "").strip()
            market_cap = cls._safe_float(company.market_cap)

        donchian_upper = cls._safe_float(latest.get("donchian_upper", 0.0))
        bb_upper = cls._safe_float(latest.get("bb_upper", 0.0))
        resistance_candidates = [
            value for value in (week_52_high, donchian_upper, bb_upper) if value > 0
        ]
        resistance = min(resistance_candidates) if resistance_candidates else 0.0

        liquidity_score = min(99.0, (cls._safe_int(quote.volume) / average_volume) * 25.0) if average_volume else 0.0

        return {
            "symbol": str(quote.symbol or "").strip().upper(),
            "company_name": company_name,
            "sector": sector,
            "industry": industry,
            "exchange": str(quote.exchange or "NSE").strip().upper(),
            "last_price": last_price,
            "open_price": cls._safe_float(quote.open_price),
            "high_price": high_price,
            "low_price": low_price,
            "previous_close": previous_close,
            "volume": cls._safe_int(quote.volume),
            "avg_volume": int(average_volume),
            "market_cap": market_cap,
            "relative_strength": max(0.0, min(99.0, relative_strength)),
            "dma_50": cls._safe_float(latest.get("ema_50", 0.0)),
            "dma_150": cls._safe_float(latest.get("ema_100", 0.0)),
            "dma_200": cls._safe_float(latest.get("ema_200", 0.0)),
            "week_52_high": week_52_high,
            "week_52_low": week_52_low,
            "liquidity_score": liquidity_score,
            "timestamp": market_data_timestamp,
            "provider_timestamp": quote.provider_timestamp,
            "last_trade_timestamp": quote.last_trade_time,
            "calculation_timestamp": evaluation_time or timezone.now(),
            "technical_scanner_fields": technical_scanner_fields,
            "ema_20": cls._safe_float(latest.get("ema_20", 0.0)),
            "ema_50": cls._safe_float(latest.get("ema_50", 0.0)),
            "ema_100": cls._safe_float(latest.get("ema_100", 0.0)),
            "ema_200": cls._safe_float(latest.get("ema_200", 0.0)),
            "rsi": cls._safe_float(latest.get("rsi", 0.0)),
            "macd": cls._safe_float(latest.get("macd", 0.0)),
            "macd_signal": cls._safe_float(latest.get("macd_signal", 0.0)),
            "macd_histogram": cls._safe_float(latest.get("macd_histogram", 0.0)),
            "adx": cls._safe_float(latest.get("adx", 0.0)),
            "plus_di": cls._safe_float(latest.get("plus_di", 0.0)),
            "minus_di": cls._safe_float(latest.get("minus_di", 0.0)),
            "atr": cls._safe_float(latest.get("atr", 0.0)),
            "vwap": cls._safe_float(latest.get("vwap", 0.0)),
            "bb_upper": bb_upper,
            "bb_middle": cls._safe_float(latest.get("bb_middle", 0.0)),
            "bb_lower": cls._safe_float(latest.get("bb_lower", 0.0)),
            "bb_width": cls._safe_float(latest.get("bb_width", 0.0)),
            "donchian_upper": donchian_upper,
            "donchian_middle": cls._safe_float(latest.get("donchian_middle", 0.0)),
            "donchian_lower": cls._safe_float(latest.get("donchian_lower", 0.0)),
            "donchian_breakout": bool(latest.get("donchian_breakout", False)),
            "supertrend": cls._safe_float(latest.get("supertrend", 0.0)),
            "supertrend_upper": cls._safe_float(latest.get("supertrend_upper", 0.0)),
            "supertrend_lower": cls._safe_float(latest.get("supertrend_lower", 0.0)),
            "resistance": resistance,
            "resistance_tests": cls._resistance_tests(candles, resistance),
            "consolidation_days": cls._consolidation_days(candles),
            **quality_mapping,
            **weekly_mapping,
            **base_quality_mapping,
            **trend_mapping,
            **volatility_mapping,
            **volume_mapping,
            **price_structure_mapping,
            **pivot_mapping,
            **vcp_mapping,
            **relative_strength_mapping,
            **supply_demand_mapping,
            **overhead_supply_mapping,
            **failed_breakout_mapping,
            **setup_lifecycle_mapping,
            **market_context_mapping,
            "data_quality": data_quality,
        }

    @classmethod
    def scan_live_market(cls, limit: int = 0) -> list[ScanReport]:
        """Scan every stored market quote once and return one report per instrument."""

        companies = cls._load_company_map()
        quotes = cls._load_quote_map()
        candles_by_instrument = cls._load_daily_candles()
        benchmark_raw_frame = BenchmarkHistoryService.load_ohlcv_frame(
            limit=RS_BENCHMARK_LOAD_OBSERVATIONS
        )
        benchmark_frame = (
            indicator_engine.calculate(benchmark_raw_frame)
            if not benchmark_raw_frame.empty
            else benchmark_raw_frame
        )
        market_context_mapping = market_context_feature_extractor.extract(
            benchmark_frame
        ).as_mapping()

        # Stored quotes can outlive an instrument's active lifecycle.
        # Only explicitly eligible companies may enter a normal scan.
        instrument_keys = sorted(set(quotes).intersection(companies))

        snapshots: list[dict[str, Any]] = []
        for key in instrument_keys:
            quote = quotes[key]
            try:
                snapshots.append(
                    cls._build_snapshot(
                        companies.get(key),
                        quote,
                        candles_by_instrument.get(key, []),
                        benchmark_frame,
                        market_context_mapping,
                    )
                )
            except Exception:
                logger.exception("Live scan failed for %s:%s", key[1], key[0])

        assign_rs_ratings(snapshots)
        if limit > 0:
            snapshots = snapshots[:limit]
        reports: list[ScanReport] = []
        for snapshot in snapshots:
            try:
                reports.append(scanner_engine.scan(snapshot))
            except Exception:
                logger.exception(
                    "Live scan failed for %s:%s",
                    snapshot.get("exchange", "NSE"),
                    snapshot.get("symbol", ""),
                )

        return reports

    @staticmethod
    def matched_strategies(report: ScanReport) -> str:
        matched = [result.strategy_name for result in report.strategies if result.passed]
        return ", ".join(matched) if matched else ""

    @classmethod
    def analyze(cls, snapshot: Mapping[str, Any]) -> dict[str, Any]:
        report = scanner_engine.scan(snapshot)
        strategies = sorted(
            report.strategies,
            key=lambda strategy: (strategy.score, strategy.weight, strategy.strategy_name),
            reverse=True,
        )

        return {
            "symbol": report.snapshot.symbol,
            "summary": {
                "total_score": report.overall_score,
                "confidence": report.confidence_score,
                "verdict": report.status,
            },
            "strategies": strategies,
            "report": report,
        }

    @classmethod
    def scan(cls, snapshot: Mapping[str, Any]) -> dict[str, Any]:
        return cls.analyze(snapshot)

    @classmethod
    def top_gainers(cls, limit: int | None = None):
        return ScannerRepository.top_gainers()[: limit or cls.DEFAULT_LIMIT]

    @classmethod
    def top_losers(cls, limit: int | None = None):
        return ScannerRepository.top_losers()[: limit or cls.DEFAULT_LIMIT]

    @classmethod
    def most_active(cls, limit: int | None = None):
        return ScannerRepository.most_active()[: limit or cls.DEFAULT_LIMIT]
