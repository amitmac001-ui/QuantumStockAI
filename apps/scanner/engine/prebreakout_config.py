from __future__ import annotations

from types import MappingProxyType
from typing import Final, Mapping


COMPONENT_WEIGHTS: Final[Mapping[str, int]] = MappingProxyType(
    {
        "trend": 20,
        "volatility_vcp": 20,
        "volume": 15,
        "relative_strength": 15,
        "pivot": 10,
        "momentum": 10,
        "market_context": 10,
    }
)

CLASSIFICATION_THRESHOLDS: Final[tuple[tuple[int, str], ...]] = (
    (85, "HIGH_QUALITY"),
    (70, "STRONG"),
    (55, "DEVELOPING"),
    (0, "WEAK"),
)

SCORE_MIN: Final[int] = 0
SCORE_MAX: Final[int] = 100

# These are configuration defaults only. Feature-specific thresholds will be
# added here as each detector is implemented and tested in later phases.
FAVORABLE_PIVOT_DISTANCE_MAX_PERCENT: Final[float] = 5.0

MIN_TREND_HISTORY: Final[int] = 200
MIN_52_WEEK_HISTORY: Final[int] = 252
RSI_SLOPE_LOOKBACK: Final[int] = 5
MACD_HISTOGRAM_LOOKBACK: Final[int] = 3
SMA_200_TREND_LOOKBACK: Final[int] = 20
MA_COMPRESSION_MAX_PERCENT: Final[float] = 3.0
MARKET_DATA_STALE_AFTER_MINUTES: Final[int] = 60
FEATURE_COMPARISON_EPSILON: Final[float] = 1e-9

VOLATILITY_MIN_HISTORY: Final[int] = 30
ATR_CONTRACTION_RECENT_LOOKBACK: Final[int] = 5
ATR_CONTRACTION_BASELINE_LOOKBACK: Final[int] = 20
ATR_CONTRACTION_MAX_RATIO: Final[float] = 0.85
BOLLINGER_SQUEEZE_LOOKBACK: Final[int] = 120
BOLLINGER_SQUEEZE_MIN_HISTORY: Final[int] = 60
BOLLINGER_SQUEEZE_QUANTILE: Final[float] = 0.20
ROLLING_RANGE_LOOKBACK: Final[int] = 10
ROLLING_RANGE_MAX_PERCENT: Final[float] = 8.0
ROLLING_RANGE_CONTRACTION_MAX_RATIO: Final[float] = 0.75
CANDLE_RANGE_RECENT_LOOKBACK: Final[int] = 5
CANDLE_RANGE_BASELINE_LOOKBACK: Final[int] = 20
CANDLE_RANGE_CONTRACTION_MAX_RATIO: Final[float] = 0.75
STDDEV_RECENT_LOOKBACK: Final[int] = 10
STDDEV_BASELINE_LOOKBACK: Final[int] = 20
STDDEV_CONTRACTION_MAX_RATIO: Final[float] = 0.75

VOLUME_MIN_HISTORY: Final[int] = 51
AVERAGE_VOLUME_SHORT_LOOKBACK: Final[int] = 20
AVERAGE_VOLUME_LONG_LOOKBACK: Final[int] = 50
VOLUME_DRY_UP_RECENT_LOOKBACK: Final[int] = 5
VOLUME_DRY_UP_BASELINE_LOOKBACK: Final[int] = 50
VOLUME_DRY_UP_MAX_RATIO: Final[float] = 0.60
VOLUME_CONSOLIDATION_LOOKBACK: Final[int] = 10
VOLUME_CONSOLIDATION_BASELINE_LOOKBACK: Final[int] = 20
VOLUME_CONSOLIDATION_MAX_RATIO: Final[float] = 0.80
VOLUME_CONSOLIDATION_MAX_PRICE_RANGE_PERCENT: Final[float] = 12.0
UP_DOWN_VOLUME_LOOKBACK: Final[int] = 20
UP_VOLUME_DOMINANCE_MIN_RATIO: Final[float] = 1.20
ACCUMULATION_LOOKBACK: Final[int] = 20
ACCUMULATION_MIN_DAYS: Final[int] = 3
VOLUME_EXPANSION_MIN_RVOL: Final[float] = 1.50
POCKET_PIVOT_LOOKBACK: Final[int] = 10
POCKET_PIVOT_MIN_RVOL: Final[float] = 1.20
POCKET_PIVOT_MIN_DOWN_DAYS: Final[int] = 2
POCKET_PIVOT_MIN_CLOSE_LOCATION: Final[float] = 0.60

PRICE_STRUCTURE_MIN_HISTORY: Final[int] = 30
SWING_WINDOW: Final[int] = 2
SWING_MIN_SEPARATION: Final[int] = 3
HIGHER_LOW_MIN_SWINGS: Final[int] = 3
HIGHER_LOW_MIN_RISE_PERCENT: Final[float] = 0.50
TIGHT_CLOSE_LOOKBACK: Final[int] = 3
TIGHT_CLOSE_MAX_RANGE_PERCENT: Final[float] = 1.50
MULTIPLE_TIGHT_CLOSE_LOOKBACK: Final[int] = 5
MULTIPLE_TIGHT_CLOSE_MAX_RANGE_PERCENT: Final[float] = 2.00
MULTIPLE_TIGHT_CLOSE_MIN_TRANSITIONS: Final[int] = 3
TIGHT_CLOSE_MAX_DAILY_CHANGE_PERCENT: Final[float] = 1.00
INSIDE_BAR_LOOKBACK: Final[int] = 5
SUPPORT_COMPRESSION_RECENT_LOOKBACK: Final[int] = 5
SUPPORT_COMPRESSION_BASELINE_LOOKBACK: Final[int] = 10
SUPPORT_COMPRESSION_MAX_RANGE_RATIO: Final[float] = 0.75
STRUCTURE_LOOKBACK: Final[int] = 30
RESISTANCE_CLUSTER_TOLERANCE_PERCENT: Final[float] = 1.50
RESISTANCE_CLUSTER_MIN_TESTS: Final[int] = 3
RESISTANCE_PROXIMITY_MAX_PERCENT: Final[float] = 5.00
FLAT_BASE_MAX_DEPTH_PERCENT: Final[float] = 15.00
ASCENDING_TRIANGLE_MAX_DEPTH_PERCENT: Final[float] = 20.00
DARVAS_BOX_LOOKBACK: Final[int] = 20
DARVAS_BOX_FORMATION_PERIOD: Final[int] = 15
DARVAS_BOX_MAX_DEPTH_PERCENT: Final[float] = 12.00
DARVAS_BOX_BOUNDARY_TOLERANCE_PERCENT: Final[float] = 0.50
DARVAS_BOX_MIN_BOUNDARY_TESTS: Final[int] = 2

RS_BENCHMARK_SYMBOL: Final[str] = "NIFTY 50"
RS_BENCHMARK_EXCHANGE: Final[str] = "NSE"
# A horizon uses this many daily observations, including the latest close.
RS_HORIZON_OBSERVATIONS: Final[Mapping[str, int]] = MappingProxyType(
    {"1m": 21, "3m": 63, "6m": 126, "12m": 252}
)
RS_COMPOSITE_WEIGHTS: Final[Mapping[str, float]] = MappingProxyType(
    {"1m": 0.20, "3m": 0.20, "6m": 0.20, "12m": 0.40}
)
RS_SLOPE_LOOKBACK: Final[int] = 20
RS_IMPROVING_MIN_SLOPE_PER_DAY: Final[float] = 0.05
RS_DETERIORATING_MAX_SLOPE_PER_DAY: Final[float] = -0.05
RS_NEW_HIGH_LOOKBACK: Final[int] = 126
RS_NEW_HIGH_TOLERANCE_PERCENT: Final[float] = 0.10
RS_ALIGNMENT_BUFFER_OBSERVATIONS: Final[int] = 20
RS_BENCHMARK_LOAD_OBSERVATIONS: Final[int] = 300

PIVOT_MIN_HISTORY: Final[int] = 30
PIVOT_LOOKBACK: Final[int] = 90
PIVOT_CONSOLIDATION_LOOKBACK: Final[int] = 30
PIVOT_SWING_WINDOW: Final[int] = 2
PIVOT_MIN_SWING_PROMINENCE_PERCENT: Final[float] = 2.00
PIVOT_MIN_TEST_SEPARATION: Final[int] = 3
PIVOT_MIN_RESISTANCE_TESTS: Final[int] = 2
PIVOT_MIN_CEILING_TESTS: Final[int] = 3
PIVOT_RESISTANCE_TOLERANCE_PERCENT: Final[float] = 1.50
PIVOT_MAX_CONSOLIDATION_DEPTH_PERCENT: Final[float] = 18.00
PIVOT_NEAR_MAX_DISTANCE_PERCENT: Final[float] = 5.00
PIVOT_TOO_FAR_DISTANCE_PERCENT: Final[float] = 10.00
PIVOT_MAX_BREACH_PERCENT: Final[float] = 5.00
PIVOT_LOW_QUALITY_SCORE: Final[int] = 60
PIVOT_SOURCE_BASE_QUALITY: Final[Mapping[str, int]] = MappingProxyType(
    {
        "FLAT_BASE_RESISTANCE": 78,
        "VCP_COMPATIBLE_PIVOT": 76,
        "REPEATED_RESISTANCE": 72,
        "CONSOLIDATION_CEILING": 68,
        "SWING_HIGH_RESISTANCE": 55,
    }
)

VCP_MIN_HISTORY: Final[int] = 60
VCP_EXTREMA_WINDOW: Final[int] = 2
VCP_MIN_CONTRACTIONS: Final[int] = 2
VCP_MAX_REPORTED_CONTRACTIONS: Final[int] = 4
VCP_MIN_CONTRACTION_DEPTH_PERCENT: Final[float] = 3.00
VCP_MAX_CONTRACTION_DEPTH_PERCENT: Final[float] = 35.00
VCP_MIN_CONTRACTION_DURATION: Final[int] = 2
VCP_MAX_CONTRACTION_DURATION: Final[int] = 30
VCP_DEPTH_DECREASE_MAX_RATIO: Final[float] = 0.95
VCP_WIDENING_MIN_RATIO: Final[float] = 1.05
VCP_HIGHER_LOW_MIN_RISE_PERCENT: Final[float] = 0.50
VCP_EXPANDING_VOLATILITY_MIN_RATIO: Final[float] = 1.10
VCP_HEAVY_DISTRIBUTION_MIN_DAYS: Final[int] = 3
VCP_MIN_INDEPENDENT_CONFIRMATIONS: Final[int] = 4
VCP_DETECTED_MIN_QUALITY_SCORE: Final[int] = 70
VCP_QUALITY_POINTS: Final[Mapping[str, int]] = MappingProxyType(
    {
        "multiple_contractions": 20,
        "decreasing_depths": 20,
        "volatility_contracting": 15,
        "volume_contracting": 15,
        "higher_lows": 15,
        "tight_near_pivot": 15,
    }
)

MARKET_CONTEXT_MIN_HISTORY: Final[int] = 200
MARKET_CONTEXT_52W_HISTORY: Final[int] = 252
MARKET_CONTEXT_SLOPE_LOOKBACK: Final[int] = 20
MARKET_CONTEXT_RECENT_HIGH_LOOKBACK: Final[int] = 63
MARKET_POSITIVE_SLOPE_MIN_PERCENT_PER_DAY: Final[float] = 0.02
MARKET_NEGATIVE_SLOPE_MAX_PERCENT_PER_DAY: Final[float] = -0.02
MARKET_MA_COMPARISON_TOLERANCE_PERCENT: Final[float] = 0.10
MARKET_HEALTHY_RSI_MIN: Final[float] = 55.0
MARKET_SUPPORTIVE_RSI_MIN: Final[float] = 50.0
MARKET_WEAK_RSI_MAX: Final[float] = 45.0
MARKET_RISK_OFF_RSI_MAX: Final[float] = 40.0
MARKET_CONTROLLED_ATR_MAX_PERCENT: Final[float] = 2.50
MARKET_HIGH_ATR_MIN_PERCENT: Final[float] = 3.50
MARKET_NEAR_HIGH_MAX_DISTANCE_PERCENT: Final[float] = 10.0
MARKET_FAR_FROM_HIGH_MIN_DISTANCE_PERCENT: Final[float] = 20.0
MARKET_ACCEPTABLE_DRAWDOWN_MAX_PERCENT: Final[float] = 12.0
MARKET_DEEP_DRAWDOWN_MIN_PERCENT: Final[float] = 20.0
MARKET_BULLISH_MIN_CONFIRMATIONS: Final[int] = 7
MARKET_SUPPORTIVE_MIN_CONFIRMATIONS: Final[int] = 5
MARKET_WEAK_MIN_RISK_SIGNALS: Final[int] = 4
MARKET_RISK_OFF_MIN_RISK_SIGNALS: Final[int] = 6

TREND_SCORE_POINTS: Final[Mapping[str, int]] = MappingProxyType(
    {
        "ema_alignment": 4,
        "price_above_sma_50": 3,
        "price_above_sma_200": 3,
        "sma_50_above_sma_200": 3,
        "sma_200_rising": 3,
        "minervini_price_trend_template": 2,
        "ma_compressed": 2,
    }
)
VOLATILITY_SCORE_POINTS: Final[Mapping[str, int]] = MappingProxyType(
    {
        "atr_contracting": 3,
        "bollinger_squeeze": 3,
        "rolling_range_compressed": 2,
        "candle_range_contracting": 2,
        "stddev_contracting": 2,
        "narrow_range": 2,
        "vcp_quality": 6,
    }
)
VOLUME_SCORE_POINTS: Final[Mapping[str, int]] = MappingProxyType(
    {
        "volume_dry_up": 3,
        "volume_contracting_in_consolidation": 3,
        "accumulation_behavior": 3,
        "up_volume_dominant": 2,
        "volume_expansion": 2,
        "pocket_pivot_style": 2,
    }
)
RS_SCORE_POINTS: Final[Mapping[str, int]] = MappingProxyType(
    {
        "rs_1m_positive": 1,
        "rs_3m_positive": 1,
        "rs_6m_positive": 1,
        "rs_12m_positive": 2,
        "rs_improving": 3,
        "rs_rating": 5,
        "rs_new_high": 2,
    }
)
PIVOT_SCORE_POINTS: Final[Mapping[str, int]] = MappingProxyType(
    {"pivot_quality": 5, "repeated_tests": 2, "near_pivot": 3}
)
MOMENTUM_SCORE_POINTS: Final[Mapping[str, int]] = MappingProxyType(
    {
        "healthy_rsi": 2,
        "positive_rsi_slope": 2,
        "rsi_reclaim_or_strength": 1,
        "rising_macd_histogram": 2,
        "expanding_macd_histogram": 1,
        "positive_directional_momentum": 1,
        "healthy_adx": 1,
    }
)
MARKET_REGIME_BASE_POINTS: Final[Mapping[str, int]] = MappingProxyType(
    {
        "STRONG": 6, "HEALTHY": 5, "NEUTRAL": 3, "WEAK": 1,
        "RISK_OFF": 0, "BULLISH": 6, "SUPPORTIVE": 5,
    }
)
MARKET_CONTEXT_QUALITY_POINTS: Final[int] = 4
SCORING_HEALTHY_RSI_MIN: Final[float] = 50.0
SCORING_HEALTHY_RSI_MAX: Final[float] = 72.0
SCORING_RSI_EXTENDED_MIN: Final[float] = 75.0
SCORING_HEALTHY_ADX_MIN: Final[float] = 20.0
SCORING_WEAK_RS_RATING_MAX: Final[int] = 40
SCORING_PRICE_EXTENSION_MIN_PERCENT: Final[float] = 3.0
SCORING_COMPONENT_CONFLUENCE_RATIO: Final[float] = 0.60
SCORING_HIGH_QUALITY_MIN_AVAILABLE_COMPONENTS: Final[int] = 6
SCORING_HIGH_QUALITY_MIN_CONFLUENT_COMPONENTS: Final[int] = 5
SCORING_STRONG_MIN_AVAILABLE_COMPONENTS: Final[int] = 5
SCORING_STRONG_MIN_CONFLUENT_COMPONENTS: Final[int] = 4
RISK_PENALTIES: Final[Mapping[str, int]] = MappingProxyType(
    {
        "PRICE_EXTENDED": 10,
        "RSI_EXTENDED": 5,
        "HIGH_VOLATILITY": 8,
        "DISTRIBUTION_VOLUME": 7,
        "RESISTANCE_TOO_FAR": 5,
        "WEAK_RELATIVE_STRENGTH": 7,
        "WEAK_MARKET_CONTEXT": 6,
        "RISK_OFF_MARKET": 10,
        "LOW_LIQUIDITY": 8,
        "INSUFFICIENT_HISTORY": 10,
        "STALE_MARKET_DATA": 10,
        "PIVOT_NOT_FOUND": 5,
    }
)
CLASSIFICATION_SCORE_CAPS: Final[Mapping[str, int]] = MappingProxyType(
    {
        "MISSING_PIVOT": 69,
        "MISSING_RELATIVE_STRENGTH": 69,
        "STALE_MARKET_DATA": 69,
        "INSUFFICIENT_HISTORY": 69,
        "LOW_LIQUIDITY": 69,
        "HIGH_VOLATILITY": 69,
        "PRICE_EXTENDED": 69,
        "RSI_EXTENDED": 84,
        "DISTRIBUTION_VOLUME": 84,
        "RESISTANCE_TOO_FAR": 69,
        "WEAK_MARKET": 69,
        "RISK_OFF_MARKET": 54,
        "HIGH_QUALITY_CONFLUENCE": 84,
        "STRONG_CONFLUENCE": 69,
        "QUALITY_PARTIAL": 69,
        "QUALITY_STALE": 54,
        "QUALITY_INVALID": 0,
    }
)


def normalize_score(value: float | int) -> int:
    """Return a deterministic integer score constrained to the public range."""

    return int(round(max(SCORE_MIN, min(float(value), SCORE_MAX))))


def classify_score(value: float | int) -> str:
    """Classify a normalized score using the configured public thresholds."""

    score = normalize_score(value)
    for minimum, classification in CLASSIFICATION_THRESHOLDS:
        if score >= minimum:
            return classification

    return "WEAK"


def validate_config() -> None:
    """Fail fast if component weights no longer form a 0-100 score."""

    if sum(COMPONENT_WEIGHTS.values()) != SCORE_MAX:
        raise ValueError("Pre-breakout component weights must total 100.")

    if any(weight < 0 for weight in COMPONENT_WEIGHTS.values()):
        raise ValueError("Pre-breakout component weights cannot be negative.")

    point_totals = {
        "trend": sum(TREND_SCORE_POINTS.values()),
        "volatility_vcp": sum(VOLATILITY_SCORE_POINTS.values()),
        "volume": sum(VOLUME_SCORE_POINTS.values()),
        "relative_strength": sum(RS_SCORE_POINTS.values()),
        "pivot": sum(PIVOT_SCORE_POINTS.values()),
        "momentum": sum(MOMENTUM_SCORE_POINTS.values()),
        "market_context": max(MARKET_REGIME_BASE_POINTS.values())
        + MARKET_CONTEXT_QUALITY_POINTS,
    }
    if point_totals != dict(COMPONENT_WEIGHTS):
        raise ValueError("Component scoring points must match configured weights.")


validate_config()
