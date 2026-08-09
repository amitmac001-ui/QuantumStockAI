from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from math import isfinite
from typing import Any

import pandas as pd
from django.utils import timezone

from .prebreakout_config import (
    FEATURE_COMPARISON_EPSILON,
    MA_COMPRESSION_MAX_PERCENT,
    MACD_HISTOGRAM_LOOKBACK,
    MARKET_DATA_STALE_AFTER_MINUTES,
    MIN_52_WEEK_HISTORY,
    MIN_TREND_HISTORY,
    RSI_SLOPE_LOOKBACK,
    SMA_200_TREND_LOOKBACK,
)


@dataclass(slots=True)
class TrendMomentumFeatures:
    ema_10: float | None = None
    sma_50: float | None = None
    sma_200: float | None = None
    ema_alignment: bool | None = None
    price_above_sma_50: bool | None = None
    price_above_sma_200: bool | None = None
    sma_50_above_sma_200: bool | None = None
    sma_200_rising: bool | None = None
    ma_compression_pct: float | None = None
    ma_compressed: bool | None = None
    price_30pct_above_52w_low: bool | None = None
    price_within_25pct_52w_high: bool | None = None
    minervini_price_trend_template: bool | None = None

    rsi_slope: float | None = None
    rsi_50_reclaim: bool | None = None
    rsi_60_strength: bool | None = None
    macd_histogram_trend: str | None = None
    macd_histogram_expanding: bool | None = None
    macd_histogram_contracting: bool | None = None
    positive_directional_momentum: bool | None = None

    data_quality: list[str] = field(default_factory=list)

    def as_mapping(self) -> dict[str, Any]:
        return asdict(self)


class TrendMomentumFeatureExtractor:
    """Derives deterministic signals from an already-enriched candle frame."""

    REQUIRED_COLUMNS = frozenset(
        {
            "close",
            "ema_10",
            "ema_20",
            "ema_50",
            "ema_200",
            "rsi",
            "macd",
            "macd_signal",
            "macd_histogram",
            "adx",
            "plus_di",
            "minus_di",
        }
    )

    @staticmethod
    def _value(frame: pd.DataFrame, column: str, offset: int = -1) -> float | None:
        if column not in frame.columns or len(frame) < abs(offset):
            return None

        try:
            value = float(frame[column].iloc[offset])
        except (TypeError, ValueError, IndexError):
            return None

        return value if isfinite(value) else None

    @staticmethod
    def _rounded(value: float | None) -> float | None:
        return round(value, 4) if value is not None else None

    @staticmethod
    def _is_stale(
        market_data_timestamp: datetime | None,
        now: datetime,
        latest_completed_session=None,
    ) -> bool:
        if market_data_timestamp is None:
            return True

        timestamp = market_data_timestamp
        if timezone.is_naive(timestamp):
            timestamp = timezone.make_aware(timestamp)
        if timezone.is_naive(now):
            now = timezone.make_aware(now)

        if latest_completed_session is not None:
            return timezone.localtime(timestamp).date() < latest_completed_session

        return now - timestamp > timedelta(minutes=MARKET_DATA_STALE_AFTER_MINUTES)

    @classmethod
    def extract(
        cls,
        frame: pd.DataFrame,
        *,
        market_data_timestamp: datetime | None = None,
        now: datetime | None = None,
        latest_completed_session=None,
    ) -> TrendMomentumFeatures:
        result = TrendMomentumFeatures()
        evaluation_time = now or timezone.now()

        if frame.empty:
            result.data_quality.extend(["MISSING_CANDLE_DATA", "INSUFFICIENT_HISTORY"])
            if cls._is_stale(
                market_data_timestamp, evaluation_time, latest_completed_session
            ):
                result.data_quality.append("STALE_MARKET_DATA")
            return result

        missing_columns = sorted(cls.REQUIRED_COLUMNS.difference(frame.columns))
        if missing_columns:
            result.data_quality.append("MISSING_INDICATOR_DATA")

        if len(frame) < MIN_TREND_HISTORY:
            result.data_quality.append("INSUFFICIENT_HISTORY")

        if cls._is_stale(
            market_data_timestamp, evaluation_time, latest_completed_session
        ):
            result.data_quality.append("STALE_MARKET_DATA")

        close = cls._value(frame, "close")
        ema_10 = cls._value(frame, "ema_10")
        ema_20 = cls._value(frame, "ema_20")
        ema_50 = cls._value(frame, "ema_50")
        ema_200 = cls._value(frame, "ema_200")

        result.ema_10 = cls._rounded(ema_10)

        sma_50_series = frame["close"].rolling(50, min_periods=50).mean()
        sma_200_series = frame["close"].rolling(200, min_periods=200).mean()
        sma_50 = cls._value(pd.DataFrame({"sma": sma_50_series}), "sma")
        sma_200 = cls._value(pd.DataFrame({"sma": sma_200_series}), "sma")
        result.sma_50 = cls._rounded(sma_50)
        result.sma_200 = cls._rounded(sma_200)

        if None not in (close, ema_10, ema_20, ema_50, ema_200):
            result.ema_alignment = bool(close > ema_10 > ema_20 > ema_50 > ema_200)
            ma_values = (ema_10, ema_20, ema_50)
            result.ma_compression_pct = cls._rounded(
                ((max(ma_values) - min(ma_values)) / close) * 100 if close > 0 else None
            )
            if result.ma_compression_pct is not None:
                result.ma_compressed = result.ma_compression_pct <= MA_COMPRESSION_MAX_PERCENT

        if close is not None and sma_50 is not None:
            result.price_above_sma_50 = close > sma_50
        if close is not None and sma_200 is not None:
            result.price_above_sma_200 = close > sma_200
        if sma_50 is not None and sma_200 is not None:
            result.sma_50_above_sma_200 = sma_50 > sma_200

        old_sma_200 = cls._value(
            pd.DataFrame({"sma": sma_200_series}),
            "sma",
            -(SMA_200_TREND_LOOKBACK + 1),
        )
        if sma_200 is not None and old_sma_200 is not None:
            result.sma_200_rising = sma_200 > old_sma_200

        if len(frame) >= MIN_52_WEEK_HISTORY and close is not None:
            lookback = frame["close"].tail(MIN_52_WEEK_HISTORY)
            week_52_low = float(lookback.min())
            week_52_high = float(lookback.max())
            if isfinite(week_52_low) and week_52_low > 0:
                result.price_30pct_above_52w_low = close >= week_52_low * 1.30
            if isfinite(week_52_high) and week_52_high > 0:
                result.price_within_25pct_52w_high = close >= week_52_high * 0.75

        trend_checks = (
            result.price_above_sma_50,
            result.price_above_sma_200,
            result.sma_50_above_sma_200,
            result.sma_200_rising,
            result.price_30pct_above_52w_low,
            result.price_within_25pct_52w_high,
        )
        if all(check is not None for check in trend_checks):
            result.minervini_price_trend_template = all(trend_checks)

        rsi = cls._value(frame, "rsi")
        previous_rsi = cls._value(frame, "rsi", -2)
        old_rsi = cls._value(frame, "rsi", -(RSI_SLOPE_LOOKBACK + 1))
        if rsi is not None and old_rsi is not None:
            result.rsi_slope = cls._rounded((rsi - old_rsi) / RSI_SLOPE_LOOKBACK)
        if rsi is not None and previous_rsi is not None:
            result.rsi_50_reclaim = previous_rsi < 50 <= rsi
        if rsi is not None:
            result.rsi_60_strength = rsi >= 60

        histogram = cls._value(frame, "macd_histogram")
        old_histogram = cls._value(
            frame,
            "macd_histogram",
            -(MACD_HISTOGRAM_LOOKBACK + 1),
        )
        if histogram is not None and old_histogram is not None:
            delta = histogram - old_histogram
            if delta > FEATURE_COMPARISON_EPSILON:
                result.macd_histogram_trend = "RISING"
            elif delta < -FEATURE_COMPARISON_EPSILON:
                result.macd_histogram_trend = "FALLING"
            else:
                result.macd_histogram_trend = "FLAT"

            result.macd_histogram_expanding = (
                histogram * old_histogram > 0 and abs(histogram) > abs(old_histogram)
            )
            result.macd_histogram_contracting = (
                histogram * old_histogram > 0 and abs(histogram) < abs(old_histogram)
            )

        plus_di = cls._value(frame, "plus_di")
        minus_di = cls._value(frame, "minus_di")
        if plus_di is not None and minus_di is not None:
            result.positive_directional_momentum = plus_di > minus_di

        return result


trend_momentum_feature_extractor = TrendMomentumFeatureExtractor()
