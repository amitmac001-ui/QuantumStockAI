from __future__ import annotations

from dataclasses import asdict, dataclass, field
from math import isfinite
from typing import Any

import pandas as pd

from .prebreakout_config import (
    MARKET_ACCEPTABLE_DRAWDOWN_MAX_PERCENT,
    MARKET_BULLISH_MIN_CONFIRMATIONS,
    MARKET_CONTEXT_52W_HISTORY,
    MARKET_CONTEXT_MIN_HISTORY,
    MARKET_CONTEXT_RECENT_HIGH_LOOKBACK,
    MARKET_CONTEXT_SLOPE_LOOKBACK,
    MARKET_CONTROLLED_ATR_MAX_PERCENT,
    MARKET_DEEP_DRAWDOWN_MIN_PERCENT,
    MARKET_FAR_FROM_HIGH_MIN_DISTANCE_PERCENT,
    MARKET_HEALTHY_RSI_MIN,
    MARKET_HIGH_ATR_MIN_PERCENT,
    MARKET_MA_COMPARISON_TOLERANCE_PERCENT,
    MARKET_NEAR_HIGH_MAX_DISTANCE_PERCENT,
    MARKET_NEGATIVE_SLOPE_MAX_PERCENT_PER_DAY,
    MARKET_POSITIVE_SLOPE_MIN_PERCENT_PER_DAY,
    MARKET_RISK_OFF_MIN_RISK_SIGNALS,
    MARKET_RISK_OFF_RSI_MAX,
    MARKET_SUPPORTIVE_MIN_CONFIRMATIONS,
    MARKET_SUPPORTIVE_RSI_MIN,
    MARKET_WEAK_MIN_RISK_SIGNALS,
    MARKET_WEAK_RSI_MAX,
)


@dataclass(slots=True)
class MarketContextFeatures:
    market_regime: str | None = None
    market_context_quality: int | None = None
    nifty_close: float | None = None
    nifty_ema_20: float | None = None
    nifty_ema_50: float | None = None
    nifty_sma_50: float | None = None
    nifty_sma_200: float | None = None
    nifty_above_20ema: bool | None = None
    nifty_above_50ema: bool | None = None
    nifty_above_50dma: bool | None = None
    nifty_above_200dma: bool | None = None
    nifty_50dma_above_200dma: bool | None = None
    nifty_ema20_slope: float | None = None
    nifty_ema50_slope: float | None = None
    nifty_ma_slope: float | None = None
    nifty_sma200_slope: float | None = None
    short_term_market_trend: str | None = None
    medium_term_market_trend: str | None = None
    long_term_market_trend: str | None = None
    nifty_rsi: float | None = None
    nifty_atr_pct: float | None = None
    market_volatility_regime: str | None = None
    nifty_distance_from_52w_high_pct: float | None = None
    nifty_recent_drawdown_pct: float | None = None
    market_reason_codes: list[str] = field(default_factory=list)
    market_risk_flags: list[str] = field(default_factory=list)
    market_data_quality: list[str] = field(default_factory=list)

    def as_mapping(self) -> dict[str, Any]:
        return asdict(self)


class MarketContextFeatureExtractor:
    """Shared NIFTY regime extraction from an indicator-enriched daily frame."""

    REQUIRED_COLUMNS = frozenset(
        {"close", "ema_20", "ema_50", "ema_200", "rsi", "atr"}
    )

    @staticmethod
    def _number(value: Any) -> float | None:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed if isfinite(parsed) else None

    @classmethod
    def _latest(cls, frame: pd.DataFrame, column: str) -> float | None:
        if column not in frame.columns or frame.empty:
            return None
        return cls._number(frame[column].iloc[-1])

    @classmethod
    def _slope(cls, values: pd.Series) -> float | None:
        numeric = pd.to_numeric(values, errors="coerce").dropna()
        if len(numeric) < MARKET_CONTEXT_SLOPE_LOOKBACK:
            return None
        recent = numeric.tail(MARKET_CONTEXT_SLOPE_LOOKBACK)
        start = cls._number(recent.iloc[0])
        end = cls._number(recent.iloc[-1])
        if start is None or end is None or start <= 0:
            return None
        return round(
            ((end / start) - 1) * 100 / (MARKET_CONTEXT_SLOPE_LOOKBACK - 1),
            6,
        )

    @staticmethod
    def _above(value: float, reference: float) -> bool:
        return value > reference * (
            1 + MARKET_MA_COMPARISON_TOLERANCE_PERCENT / 100
        )

    @staticmethod
    def _below(value: float, reference: float) -> bool:
        return value < reference * (
            1 - MARKET_MA_COMPARISON_TOLERANCE_PERCENT / 100
        )

    @staticmethod
    def _trend(positive: bool, negative: bool) -> str:
        if positive:
            return "BULLISH"
        if negative:
            return "BEARISH"
        return "NEUTRAL"

    @classmethod
    def extract(cls, frame: pd.DataFrame) -> MarketContextFeatures:
        result = MarketContextFeatures()
        if frame.empty:
            result.market_data_quality.extend(
                ["BENCHMARK_HISTORY_UNAVAILABLE", "INSUFFICIENT_MARKET_HISTORY"]
            )
            return result
        missing = cls.REQUIRED_COLUMNS.difference(frame.columns)
        if missing:
            result.market_data_quality.append("MARKET_INDICATOR_DATA_UNAVAILABLE")
            return result
        if len(frame) < MARKET_CONTEXT_MIN_HISTORY:
            result.market_data_quality.append("INSUFFICIENT_MARKET_HISTORY")
            return result
        if len(frame) < MARKET_CONTEXT_52W_HISTORY:
            result.market_data_quality.append("INSUFFICIENT_MARKET_52W_HISTORY")

        working = frame.copy()
        working["sma_50"] = working["close"].rolling(50, min_periods=50).mean()
        working["sma_200"] = working["close"].rolling(200, min_periods=200).mean()

        result.nifty_close = cls._latest(working, "close")
        result.nifty_ema_20 = cls._latest(working, "ema_20")
        result.nifty_ema_50 = cls._latest(working, "ema_50")
        result.nifty_sma_50 = cls._latest(working, "sma_50")
        result.nifty_sma_200 = cls._latest(working, "sma_200")
        result.nifty_rsi = cls._latest(working, "rsi")
        atr = cls._latest(working, "atr")
        required_values = (
            result.nifty_close,
            result.nifty_ema_20,
            result.nifty_ema_50,
            result.nifty_sma_50,
            result.nifty_sma_200,
            result.nifty_rsi,
            atr,
        )
        if any(value is None for value in required_values):
            result.market_data_quality.append("MARKET_INDICATOR_DATA_UNAVAILABLE")
            return result

        close = result.nifty_close
        result.nifty_above_20ema = cls._above(close, result.nifty_ema_20)
        result.nifty_above_50ema = cls._above(close, result.nifty_ema_50)
        result.nifty_above_50dma = cls._above(close, result.nifty_sma_50)
        result.nifty_above_200dma = cls._above(close, result.nifty_sma_200)
        result.nifty_50dma_above_200dma = cls._above(
            result.nifty_sma_50, result.nifty_sma_200
        )
        result.nifty_ema20_slope = cls._slope(working["ema_20"])
        result.nifty_ema50_slope = cls._slope(working["ema_50"])
        result.nifty_ma_slope = cls._slope(working["sma_50"])
        result.nifty_sma200_slope = cls._slope(working["sma_200"])

        result.nifty_atr_pct = round(atr / close * 100, 4)
        if result.nifty_atr_pct <= MARKET_CONTROLLED_ATR_MAX_PERCENT:
            result.market_volatility_regime = "CONTROLLED"
        elif result.nifty_atr_pct >= MARKET_HIGH_ATR_MIN_PERCENT:
            result.market_volatility_regime = "HIGH"
        else:
            result.market_volatility_regime = "ELEVATED"

        high_52 = cls._number(working["high"].tail(MARKET_CONTEXT_52W_HISTORY).max())
        recent_high = cls._number(
            working["high"].tail(MARKET_CONTEXT_RECENT_HIGH_LOOKBACK).max()
        )
        if high_52 is not None and high_52 > 0:
            result.nifty_distance_from_52w_high_pct = round(
                max((high_52 - close) / high_52 * 100, 0.0), 4
            )
        if recent_high is not None and recent_high > 0:
            result.nifty_recent_drawdown_pct = round(
                max((recent_high - close) / recent_high * 100, 0.0), 4
            )

        positive_slope = (
            result.nifty_ma_slope is not None
            and result.nifty_ma_slope >= MARKET_POSITIVE_SLOPE_MIN_PERCENT_PER_DAY
        )
        negative_slope = (
            result.nifty_ma_slope is not None
            and result.nifty_ma_slope <= MARKET_NEGATIVE_SLOPE_MAX_PERCENT_PER_DAY
        )
        below_20 = cls._below(close, result.nifty_ema_20)
        below_50 = cls._below(close, result.nifty_sma_50)
        below_200 = cls._below(close, result.nifty_sma_200)
        bearish_alignment = cls._below(result.nifty_sma_50, result.nifty_sma_200)
        healthy_momentum = result.nifty_rsi >= MARKET_HEALTHY_RSI_MIN
        weak_momentum = result.nifty_rsi <= MARKET_WEAK_RSI_MAX
        risk_off_momentum = result.nifty_rsi <= MARKET_RISK_OFF_RSI_MAX
        controlled_volatility = result.market_volatility_regime == "CONTROLLED"
        high_volatility = result.market_volatility_regime == "HIGH"
        near_high = (
            result.nifty_distance_from_52w_high_pct is not None
            and result.nifty_distance_from_52w_high_pct
            <= MARKET_NEAR_HIGH_MAX_DISTANCE_PERCENT
        )
        far_from_high = (
            result.nifty_distance_from_52w_high_pct is not None
            and result.nifty_distance_from_52w_high_pct
            >= MARKET_FAR_FROM_HIGH_MIN_DISTANCE_PERCENT
        )
        acceptable_drawdown = (
            result.nifty_recent_drawdown_pct is not None
            and result.nifty_recent_drawdown_pct
            <= MARKET_ACCEPTABLE_DRAWDOWN_MAX_PERCENT
        )
        deep_drawdown = (
            result.nifty_recent_drawdown_pct is not None
            and result.nifty_recent_drawdown_pct
            >= MARKET_DEEP_DRAWDOWN_MIN_PERCENT
        )

        result.short_term_market_trend = cls._trend(
            result.nifty_above_20ema
            and result.nifty_ema20_slope is not None
            and result.nifty_ema20_slope >= MARKET_POSITIVE_SLOPE_MIN_PERCENT_PER_DAY
            and result.nifty_rsi >= MARKET_SUPPORTIVE_RSI_MIN,
            below_20
            and result.nifty_ema20_slope is not None
            and result.nifty_ema20_slope <= MARKET_NEGATIVE_SLOPE_MAX_PERCENT_PER_DAY
            and result.nifty_rsi < MARKET_SUPPORTIVE_RSI_MIN,
        )
        result.medium_term_market_trend = cls._trend(
            result.nifty_above_50dma and positive_slope,
            below_50 and negative_slope,
        )
        result.long_term_market_trend = cls._trend(
            result.nifty_above_200dma
            and result.nifty_50dma_above_200dma
            and result.nifty_sma200_slope is not None
            and result.nifty_sma200_slope > 0,
            below_200
            and bearish_alignment
            and result.nifty_sma200_slope is not None
            and result.nifty_sma200_slope < 0,
        )

        positive_signals = (
            result.nifty_above_20ema,
            result.nifty_above_50dma,
            result.nifty_above_200dma,
            result.nifty_50dma_above_200dma,
            positive_slope,
            healthy_momentum,
            controlled_volatility,
            near_high,
            acceptable_drawdown,
        )
        risk_signals = (
            below_20,
            below_50,
            below_200,
            bearish_alignment,
            negative_slope,
            weak_momentum,
            high_volatility,
            far_from_high,
            deep_drawdown,
        )
        positive_count = sum(positive_signals)
        risk_count = sum(risk_signals)
        result.market_context_quality = round(positive_count / len(positive_signals) * 100)

        bullish_confluence = bool(
            positive_count >= MARKET_BULLISH_MIN_CONFIRMATIONS
            and result.nifty_above_20ema
            and result.nifty_above_50dma
            and result.nifty_above_200dma
            and result.nifty_50dma_above_200dma
            and positive_slope
            and healthy_momentum
            and not high_volatility
            and near_high
        )
        supportive_confluence = bool(
            positive_count >= MARKET_SUPPORTIVE_MIN_CONFIRMATIONS
            and result.nifty_above_50dma
            and result.nifty_above_200dma
            and result.nifty_ma_slope is not None
            and result.nifty_ma_slope >= 0
            and result.nifty_rsi >= MARKET_SUPPORTIVE_RSI_MIN
            and not high_volatility
        )
        risk_off_confluence = bool(
            risk_count >= MARKET_RISK_OFF_MIN_RISK_SIGNALS
            and below_50
            and below_200
            and negative_slope
            and risk_off_momentum
            and (high_volatility or deep_drawdown)
        )
        weak_confluence = bool(
            risk_count >= MARKET_WEAK_MIN_RISK_SIGNALS
            and below_50
            and (below_200 or negative_slope)
        )
        if bullish_confluence:
            result.market_regime = "STRONG"
        elif supportive_confluence:
            result.market_regime = "HEALTHY"
        elif risk_off_confluence:
            result.market_regime = "RISK_OFF"
        elif weak_confluence:
            result.market_regime = "WEAK"
        else:
            result.market_regime = "NEUTRAL"

        reason_pairs = (
            (result.nifty_above_20ema, "NIFTY_ABOVE_20EMA"),
            (result.nifty_above_50dma, "NIFTY_ABOVE_50DMA"),
            (result.nifty_above_200dma, "NIFTY_ABOVE_200DMA"),
            (result.nifty_50dma_above_200dma, "BULLISH_MA_ALIGNMENT"),
            (positive_slope, "POSITIVE_MA_SLOPE"),
            (healthy_momentum, "HEALTHY_NIFTY_MOMENTUM"),
            (controlled_volatility, "CONTROLLED_MARKET_VOLATILITY"),
            (near_high, "NIFTY_NEAR_52W_HIGH"),
            (acceptable_drawdown, "ACCEPTABLE_MARKET_DRAWDOWN"),
        )
        result.market_reason_codes = [
            reason for confirmed, reason in reason_pairs if confirmed
        ]
        risk_pairs = (
            (below_20, "NIFTY_BELOW_20EMA"),
            (below_50, "NIFTY_BELOW_50DMA"),
            (below_200, "NIFTY_BELOW_200DMA"),
            (bearish_alignment, "BEARISH_MA_ALIGNMENT"),
            (negative_slope, "NEGATIVE_MA_SLOPE"),
            (weak_momentum, "WEAK_NIFTY_MOMENTUM"),
            (high_volatility, "HIGH_MARKET_VOLATILITY"),
            (far_from_high, "NIFTY_FAR_FROM_52W_HIGH"),
            (deep_drawdown, "DEEP_MARKET_DRAWDOWN"),
        )
        result.market_risk_flags = [flag for detected, flag in risk_pairs if detected]
        return result


market_context_feature_extractor = MarketContextFeatureExtractor()
