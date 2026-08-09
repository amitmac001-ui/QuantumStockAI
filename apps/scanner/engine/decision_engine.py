from __future__ import annotations

import pandas as pd

from apps.market.indicators.engine import indicator_engine

from apps.scanner.engine.prebreakout_engine import prebreakout_engine

from dataclasses import dataclass, field
from datetime import datetime
from math import isnan
from typing import Any, Iterable, Mapping, Optional


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        v = float(value)
        if isnan(v):
            return default
        return v
    except (TypeError, ValueError):
        return default


def _optional_bool(value: Any) -> bool | None:
    return None if value is None else bool(value)


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    parsed = _safe_float(value, default=float("nan"))
    return None if isnan(parsed) else parsed


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _percent_change(last_price: float, previous_close: float) -> float:
    if previous_close <= 0:
        return 0.0
    return ((last_price - previous_close) / previous_close) * 100.0


def _volume_surge(volume: int, avg_volume: int) -> float:
    if avg_volume <= 0:
        return 1.0
    return volume / avg_volume


def _has_any(*values: Any) -> bool:
    for value in values:
        if value is None:
            continue
        if isinstance(value, bool):
            if value:
                return True
            continue
        if isinstance(value, (int, float)) and value != 0:
            return True
        if isinstance(value, str) and value.strip():
            return True
    return False


@dataclass(slots=True)
class StockSnapshot:
    symbol: str
    company_name: str = ""
    sector: str = ""
    industry: str = ""
    exchange: str = "NSE"

    last_price: float = 0.0
    open_price: float = 0.0
    high_price: float = 0.0
    low_price: float = 0.0
    previous_close: float = 0.0

    volume: int = 0
    avg_volume: int = 0
    avg_volume_5: float | None = None
    avg_volume_10: float | None = None
    avg_volume_20: float | None = None
    avg_volume_50: float | None = None
    volume_ratio_5d: float | None = None
    volume_ratio_10d: float | None = None
    volume_ratio_20d: float | None = None
    volume_ratio_50d: float | None = None
    rvol: float | None = None
    volume_dry_up_ratio: float | None = None
    volume_dry_up: bool | None = None
    consolidation_volume_ratio: float | None = None
    volume_contracting_in_consolidation: bool | None = None
    up_volume: float | None = None
    down_volume: float | None = None
    up_down_volume_ratio: float | None = None
    up_volume_dominant: bool | None = None
    accumulation_days: int | None = None
    distribution_days: int | None = None
    accumulation_behavior: bool | None = None
    volume_expansion: bool | None = None
    pocket_pivot_style: bool | None = None
    abnormal_volume: bool | None = None
    zero_volume_ratio_50d: float | None = None
    volume_dry_up_near_pivot: bool | None = None
    volume_reason_codes: list[str] = field(default_factory=list)

    market_cap: float = 0.0
    pe_ratio: float = 0.0
    roe: float = 0.0
    roce: float = 0.0
    debt_to_equity: float = 0.0

    sales_growth: float = 0.0
    profit_growth: float = 0.0
    earnings_growth: float = 0.0

    relative_strength: float = 0.0
    # Deterministic Phase 6 market-relative strength; deliberately separate from RSI.
    rs_1m_pct: float | None = None
    rs_3m_pct: float | None = None
    rs_6m_pct: float | None = None
    rs_12m_pct: float | None = None
    rs_slope_pct_per_day: float | None = None
    rs_acceleration: float | None = None
    rs_trend_status: str | None = None
    rs_improving: bool | None = None
    rs_deteriorating: bool | None = None
    rs_new_high: bool | None = None
    rs_line_near_high: bool | None = None
    rs_line_distance_from_high_pct: float | None = None
    rs_line_leading_price: bool | None = None
    sector_rs_status: str = "DATA_UNAVAILABLE"
    rs_composite_score: float | None = None
    rs_rating: int | None = None
    rs_reason_codes: list[str] = field(default_factory=list)
    dma_50: float = 0.0
    dma_150: float = 0.0
    dma_200: float = 0.0

    week_52_high: float = 0.0
    week_52_low: float = 0.0
    atr: float = 0.0
    atr_pct: float | None = None
    atr_contraction_ratio: float | None = None
    atr_contracting: bool | None = None
    beta: float = 0.0

    cashflow_positive: bool = False
    institutional_holding_growth: float = 0.0
    sector_strength: float = 0.0
    liquidity_score: float = 0.0

    timestamp: Optional[datetime] = None
    provider_timestamp: Optional[datetime] = None
    last_trade_timestamp: Optional[datetime] = None

        # ===== Technical Indicators =====

    ema_20: float = 0.0
    ema_50: float = 0.0
    ema_100: float = 0.0
    ema_200: float = 0.0

    # Deterministic Phase 2 trend features. None means unavailable.
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

    rsi: float = 0.0

    macd: float = 0.0
    macd_signal: float = 0.0
    macd_histogram: float = 0.0

    adx: float = 0.0
    plus_di: float = 0.0
    minus_di: float = 0.0

    # Deterministic Phase 2 momentum features. None means unavailable.
    rsi_slope: float | None = None
    rsi_50_reclaim: bool | None = None
    rsi_60_strength: bool | None = None
    macd_histogram_trend: str | None = None
    macd_histogram_expanding: bool | None = None
    macd_histogram_contracting: bool | None = None
    positive_directional_momentum: bool | None = None

    data_quality: list[str] = field(default_factory=list)
    data_quality_state: str = "INVALID"
    latest_daily_session: Any = None
    expected_daily_session: Any = None
    lookback_sessions: int = 0
    missing_session_count: int = 0
    duplicate_session_count: int = 0
    invalid_ohlc_count: int = 0
    impossible_price_count: int = 0
    negative_volume_count: int = 0
    zero_volume_count: int = 0
    abnormal_volume_count: int = 0
    invalid_timestamp_count: int = 0
    provider_flag_count: int = 0
    data_quality_reason_codes: list[str] = field(default_factory=list)

    weekly_observations: int = 0
    weekly_trend: str | None = None
    weekly_close: float | None = None
    weekly_sma_10: float | None = None
    weekly_sma_30: float | None = None
    weekly_sma_40: float | None = None
    weekly_ma_alignment: bool | None = None
    weekly_price_structure: str | None = None
    weekly_contraction_ratio: float | None = None
    weekly_contraction: bool | None = None
    daily_weekly_alignment: bool | None = None
    weekly_reason_codes: list[str] = field(default_factory=list)

    vwap: float = 0.0

    bb_upper: float = 0.0
    bb_middle: float = 0.0
    bb_lower: float = 0.0
    bb_width: float = 0.0
    bb_width_pct: float | None = None
    bb_width_percentile: float | None = None
    bollinger_squeeze: bool | None = None

    nr4: bool | None = None
    nr7: bool | None = None
    rolling_range_pct: float | None = None
    rolling_range_contraction_ratio: float | None = None
    rolling_range_compressed: bool | None = None
    candle_range_contraction_ratio: float | None = None
    candle_range_contracting: bool | None = None
    stddev_contraction_ratio: float | None = None
    stddev_contracting: bool | None = None
    volatility_reason_codes: list[str] = field(default_factory=list)

    # Deterministic Phase 5 price-structure features. None means unavailable.
    higher_lows: bool | None = None
    swing_low_count: int | None = None
    tight_closes: bool | None = None
    tight_close_range_pct: float | None = None
    multiple_tight_closes: bool | None = None
    tight_close_transition_count: int | None = None
    inside_bar: bool | None = None
    inside_bar_count: int | None = None
    support_compression: bool | None = None
    support_range_contraction_ratio: float | None = None
    price_clustered_near_resistance: bool | None = None
    resistance_cluster_test_count: int | None = None
    resistance_cluster_spread_pct: float | None = None
    flat_base: bool | None = None
    flat_base_depth_pct: float | None = None
    ascending_triangle: bool | None = None
    darvas_consolidation: bool | None = None
    darvas_box_depth_pct: float | None = None
    price_structure_reason_codes: list[str] = field(default_factory=list)

    # Deterministic Phase 7 pivot features; separate from legacy resistance fields.
    breakout_level: float | None = None
    distance_to_breakout_pct: float | None = None
    pivot_source: str | None = None
    pivot_test_count: int | None = None
    pivot_quality_score: int | None = None
    near_pivot: bool | None = None
    already_above_pivot: bool | None = None
    resistance_too_far: bool | None = None
    resistance_clustered: bool | None = None
    pivot_candidate_count: int = 0
    pivot_candidates: list[dict[str, Any]] = field(default_factory=list)
    pivot_reason_codes: list[str] = field(default_factory=list)
    pivot_quality_flags: list[str] = field(default_factory=list)

    base_duration_sessions: int | None = None
    base_depth_pct: float | None = None
    base_quality_score: int | None = None
    progressively_smaller_contractions: bool | None = None
    overhead_resistance_pct: float | None = None
    overhead_resistance_clear: bool | None = None
    premature_breakout: bool | None = None
    already_extended: bool | None = None
    base_reason_codes: list[str] = field(default_factory=list)
    base_risk_flags: list[str] = field(default_factory=list)

    # Deterministic Phase 8 VCP feature set; not part of final score yet.
    vcp_detected: bool | None = None
    vcp_invalid: bool | None = None
    vcp_quality_score: int | None = None
    contraction_count: int = 0
    contraction_depths: list[float] = field(default_factory=list)
    contraction_durations: list[int] = field(default_factory=list)
    depths_decreasing: bool | None = None
    t1_t2_t3_tightening: bool | None = None
    volatility_contracting: bool | None = None
    volume_contracting: bool | None = None
    tight_near_pivot: bool | None = None
    higher_lows_present: bool | None = None
    independent_confirmation_count: int = 0
    vcp_reason_codes: list[str] = field(default_factory=list)
    vcp_risk_flags: list[str] = field(default_factory=list)
    vcp_data_quality: list[str] = field(default_factory=list)

    # Deterministic Pre-Breakout Intelligence V3; independent from production score.
    demand_pressure_score: int | None = None
    supply_pressure_score: int | None = None
    accumulation_distribution_balance: float | None = None
    pullback_volume_contracting: bool | None = None
    resistance_absorption_detected: bool | None = None
    selling_pressure_declining: bool | None = None
    demand_expansion_detected: bool | None = None
    price_progress_per_volume: float | None = None
    supply_demand_reason_codes: list[str] = field(default_factory=list)
    supply_demand_risk_flags: list[str] = field(default_factory=list)

    overhead_supply_score: int | None = None
    overhead_supply_clear: bool | None = None
    nearest_overhead_resistance: float | None = None
    distance_to_overhead_resistance_pct: float | None = None
    overhead_resistance_count: int | None = None
    overhead_high_volume_zone_count: int | None = None
    overhead_supply_reason_codes: list[str] = field(default_factory=list)
    overhead_supply_risk_flags: list[str] = field(default_factory=list)

    failed_breakout_count: int | None = None
    recent_failed_breakout: bool | None = None
    days_since_failed_breakout: int | None = None
    same_zone_failure_count: int | None = None
    failure_severity: str | None = None
    failed_breakout_reason_codes: list[str] = field(default_factory=list)
    failed_breakout_risk_flags: list[str] = field(default_factory=list)

    setup_lifecycle: str = "NO_SETUP"
    setup_readiness_score: int = 0
    sector_context_status: str = "SECTOR_CONTEXT_UNAVAILABLE"
    setup_reason_codes: list[str] = field(default_factory=list)
    setup_risk_flags: list[str] = field(default_factory=list)

    # Deterministic Phase 9 shared NIFTY market context; not scored yet.
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

    donchian_upper: float = 0.0
    donchian_middle: float = 0.0
    donchian_lower: float = 0.0
    donchian_breakout: bool = False

    supertrend: float = 0.0
    supertrend_upper: float = 0.0
    supertrend_lower: float = 0.0

    resistance: float = 0.0

    support: float = 0.0

    distance_from_resistance: float = 0.0

    resistance_tests: int = 0

    consolidation_days: int = 0

    breakout_probability: float = 0.0

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "StockSnapshot":
        symbol = str(data.get("symbol", "")).strip().upper()
        return cls(
            symbol=symbol,
            company_name=str(data.get("company_name", "")).strip(),
            sector=str(data.get("sector", "")).strip(),
            industry=str(data.get("industry", "")).strip(),
            exchange=str(data.get("exchange", "NSE")).strip().upper(),
            last_price=_safe_float(data.get("last_price")),
            open_price=_safe_float(data.get("open_price")),
            high_price=_safe_float(data.get("high_price")),
            low_price=_safe_float(data.get("low_price")),
            previous_close=_safe_float(data.get("previous_close")),
            volume=_safe_int(data.get("volume")),
            avg_volume=_safe_int(data.get("avg_volume")),
            avg_volume_5=_optional_float(data.get("avg_volume_5")),
            avg_volume_10=_optional_float(data.get("avg_volume_10")),
            avg_volume_20=_optional_float(data.get("avg_volume_20")),
            avg_volume_50=_optional_float(data.get("avg_volume_50")),
            volume_ratio_5d=_optional_float(data.get("volume_ratio_5d")),
            volume_ratio_10d=_optional_float(data.get("volume_ratio_10d")),
            volume_ratio_20d=_optional_float(data.get("volume_ratio_20d")),
            volume_ratio_50d=_optional_float(data.get("volume_ratio_50d")),
            rvol=_optional_float(data.get("rvol")),
            volume_dry_up_ratio=_optional_float(data.get("volume_dry_up_ratio")),
            volume_dry_up=_optional_bool(data.get("volume_dry_up")),
            consolidation_volume_ratio=_optional_float(
                data.get("consolidation_volume_ratio")
            ),
            volume_contracting_in_consolidation=_optional_bool(
                data.get("volume_contracting_in_consolidation")
            ),
            up_volume=_optional_float(data.get("up_volume")),
            down_volume=_optional_float(data.get("down_volume")),
            up_down_volume_ratio=_optional_float(data.get("up_down_volume_ratio")),
            up_volume_dominant=_optional_bool(data.get("up_volume_dominant")),
            accumulation_days=(
                None
                if data.get("accumulation_days") is None
                else _safe_int(data.get("accumulation_days"))
            ),
            distribution_days=(
                None
                if data.get("distribution_days") is None
                else _safe_int(data.get("distribution_days"))
            ),
            accumulation_behavior=_optional_bool(data.get("accumulation_behavior")),
            volume_expansion=_optional_bool(data.get("volume_expansion")),
            pocket_pivot_style=_optional_bool(data.get("pocket_pivot_style")),
            abnormal_volume=_optional_bool(data.get("abnormal_volume")),
            zero_volume_ratio_50d=_optional_float(data.get("zero_volume_ratio_50d")),
            volume_dry_up_near_pivot=_optional_bool(
                data.get("volume_dry_up_near_pivot")
            ),
            volume_reason_codes=[
                str(code) for code in (data.get("volume_reason_codes") or [])
            ],
            market_cap=_safe_float(data.get("market_cap")),
            pe_ratio=_safe_float(data.get("pe_ratio")),
            roe=_safe_float(data.get("roe")),
            roce=_safe_float(data.get("roce")),
            debt_to_equity=_safe_float(data.get("debt_to_equity")),
            sales_growth=_safe_float(data.get("sales_growth")),
            profit_growth=_safe_float(data.get("profit_growth")),
            earnings_growth=_safe_float(data.get("earnings_growth")),
            relative_strength=_safe_float(data.get("relative_strength")),
            rs_1m_pct=_optional_float(data.get("rs_1m_pct")),
            rs_3m_pct=_optional_float(data.get("rs_3m_pct")),
            rs_6m_pct=_optional_float(data.get("rs_6m_pct")),
            rs_12m_pct=_optional_float(data.get("rs_12m_pct")),
            rs_slope_pct_per_day=_optional_float(
                data.get("rs_slope_pct_per_day")
            ),
            rs_acceleration=_optional_float(data.get("rs_acceleration")),
            rs_trend_status=(
                None
                if data.get("rs_trend_status") is None
                else str(data.get("rs_trend_status"))
            ),
            rs_improving=_optional_bool(data.get("rs_improving")),
            rs_deteriorating=_optional_bool(data.get("rs_deteriorating")),
            rs_new_high=_optional_bool(data.get("rs_new_high")),
            rs_line_near_high=_optional_bool(data.get("rs_line_near_high")),
            rs_line_distance_from_high_pct=_optional_float(
                data.get("rs_line_distance_from_high_pct")
            ),
            rs_line_leading_price=_optional_bool(data.get("rs_line_leading_price")),
            sector_rs_status=str(data.get("sector_rs_status", "DATA_UNAVAILABLE")),
            rs_composite_score=_optional_float(data.get("rs_composite_score")),
            rs_rating=(
                None
                if data.get("rs_rating") is None
                else _safe_int(data.get("rs_rating"))
            ),
            rs_reason_codes=[
                str(code) for code in (data.get("rs_reason_codes") or [])
            ],
            dma_50=_safe_float(data.get("dma_50")),
            dma_150=_safe_float(data.get("dma_150")),
            dma_200=_safe_float(data.get("dma_200")),
            week_52_high=_safe_float(data.get("week_52_high")),
            week_52_low=_safe_float(data.get("week_52_low")),
            atr=_safe_float(data.get("atr")),
            atr_pct=_optional_float(data.get("atr_pct")),
            atr_contraction_ratio=_optional_float(
                data.get("atr_contraction_ratio")
            ),
            atr_contracting=_optional_bool(data.get("atr_contracting")),
            beta=_safe_float(data.get("beta")),
            cashflow_positive=bool(data.get("cashflow_positive", False)),
            institutional_holding_growth=_safe_float(data.get("institutional_holding_growth")),
            sector_strength=_safe_float(data.get("sector_strength")),
            liquidity_score=_safe_float(data.get("liquidity_score")),

            timestamp=data.get("timestamp"),
            provider_timestamp=data.get("provider_timestamp"),
            last_trade_timestamp=data.get("last_trade_timestamp"),

            ema_20=_safe_float(data.get("ema_20")),
            ema_50=_safe_float(data.get("ema_50")),
            ema_100=_safe_float(data.get("ema_100")),
            ema_200=_safe_float(data.get("ema_200")),
            ema_10=_optional_float(data.get("ema_10")),
            sma_50=_optional_float(data.get("sma_50")),
            sma_200=_optional_float(data.get("sma_200")),
            ema_alignment=_optional_bool(data.get("ema_alignment")),
            price_above_sma_50=_optional_bool(data.get("price_above_sma_50")),
            price_above_sma_200=_optional_bool(data.get("price_above_sma_200")),
            sma_50_above_sma_200=_optional_bool(data.get("sma_50_above_sma_200")),
            sma_200_rising=_optional_bool(data.get("sma_200_rising")),
            ma_compression_pct=_optional_float(data.get("ma_compression_pct")),
            ma_compressed=_optional_bool(data.get("ma_compressed")),
            price_30pct_above_52w_low=_optional_bool(
                data.get("price_30pct_above_52w_low")
            ),
            price_within_25pct_52w_high=_optional_bool(
                data.get("price_within_25pct_52w_high")
            ),
            minervini_price_trend_template=_optional_bool(
                data.get("minervini_price_trend_template")
            ),

            rsi=_safe_float(data.get("rsi")),

            macd=_safe_float(data.get("macd")),
            macd_signal=_safe_float(data.get("macd_signal")),
            macd_histogram=_safe_float(data.get("macd_histogram")),

            adx=_safe_float(data.get("adx")),
            plus_di=_safe_float(data.get("plus_di")),
            minus_di=_safe_float(data.get("minus_di")),
            rsi_slope=_optional_float(data.get("rsi_slope")),
            rsi_50_reclaim=_optional_bool(data.get("rsi_50_reclaim")),
            rsi_60_strength=_optional_bool(data.get("rsi_60_strength")),
            macd_histogram_trend=data.get("macd_histogram_trend"),
            macd_histogram_expanding=_optional_bool(
                data.get("macd_histogram_expanding")
            ),
            macd_histogram_contracting=_optional_bool(
                data.get("macd_histogram_contracting")
            ),
            positive_directional_momentum=_optional_bool(
                data.get("positive_directional_momentum")
            ),
            data_quality=[str(flag) for flag in (data.get("data_quality") or [])],
            data_quality_state=str(data.get("data_quality_state", "INVALID")),
            latest_daily_session=data.get("latest_daily_session"),
            expected_daily_session=data.get("expected_daily_session"),
            lookback_sessions=_safe_int(data.get("lookback_sessions")),
            missing_session_count=_safe_int(data.get("missing_session_count")),
            duplicate_session_count=_safe_int(data.get("duplicate_session_count")),
            invalid_ohlc_count=_safe_int(data.get("invalid_ohlc_count")),
            impossible_price_count=_safe_int(data.get("impossible_price_count")),
            negative_volume_count=_safe_int(data.get("negative_volume_count")),
            zero_volume_count=_safe_int(data.get("zero_volume_count")),
            abnormal_volume_count=_safe_int(data.get("abnormal_volume_count")),
            invalid_timestamp_count=_safe_int(data.get("invalid_timestamp_count")),
            provider_flag_count=_safe_int(data.get("provider_flag_count")),
            data_quality_reason_codes=[
                str(code) for code in (data.get("data_quality_reason_codes") or [])
            ],
            weekly_observations=_safe_int(data.get("weekly_observations")),
            weekly_trend=data.get("weekly_trend"),
            weekly_close=_optional_float(data.get("weekly_close")),
            weekly_sma_10=_optional_float(data.get("weekly_sma_10")),
            weekly_sma_30=_optional_float(data.get("weekly_sma_30")),
            weekly_sma_40=_optional_float(data.get("weekly_sma_40")),
            weekly_ma_alignment=_optional_bool(data.get("weekly_ma_alignment")),
            weekly_price_structure=data.get("weekly_price_structure"),
            weekly_contraction_ratio=_optional_float(data.get("weekly_contraction_ratio")),
            weekly_contraction=_optional_bool(data.get("weekly_contraction")),
            daily_weekly_alignment=_optional_bool(data.get("daily_weekly_alignment")),
            weekly_reason_codes=[str(code) for code in (data.get("weekly_reason_codes") or [])],

            vwap=_safe_float(data.get("vwap")),

            bb_upper=_safe_float(data.get("bb_upper")),
            bb_middle=_safe_float(data.get("bb_middle")),
            bb_lower=_safe_float(data.get("bb_lower")),
            bb_width=_safe_float(data.get("bb_width")),
            bb_width_pct=_optional_float(data.get("bb_width_pct")),
            bb_width_percentile=_optional_float(
                data.get("bb_width_percentile")
            ),
            bollinger_squeeze=_optional_bool(data.get("bollinger_squeeze")),
            nr4=_optional_bool(data.get("nr4")),
            nr7=_optional_bool(data.get("nr7")),
            rolling_range_pct=_optional_float(data.get("rolling_range_pct")),
            rolling_range_contraction_ratio=_optional_float(
                data.get("rolling_range_contraction_ratio")
            ),
            rolling_range_compressed=_optional_bool(
                data.get("rolling_range_compressed")
            ),
            candle_range_contraction_ratio=_optional_float(
                data.get("candle_range_contraction_ratio")
            ),
            candle_range_contracting=_optional_bool(
                data.get("candle_range_contracting")
            ),
            stddev_contraction_ratio=_optional_float(
                data.get("stddev_contraction_ratio")
            ),
            stddev_contracting=_optional_bool(data.get("stddev_contracting")),
            volatility_reason_codes=[
                str(code) for code in (data.get("volatility_reason_codes") or [])
            ],
            higher_lows=_optional_bool(data.get("higher_lows")),
            swing_low_count=(
                None
                if data.get("swing_low_count") is None
                else _safe_int(data.get("swing_low_count"))
            ),
            tight_closes=_optional_bool(data.get("tight_closes")),
            tight_close_range_pct=_optional_float(
                data.get("tight_close_range_pct")
            ),
            multiple_tight_closes=_optional_bool(
                data.get("multiple_tight_closes")
            ),
            tight_close_transition_count=(
                None
                if data.get("tight_close_transition_count") is None
                else _safe_int(data.get("tight_close_transition_count"))
            ),
            inside_bar=_optional_bool(data.get("inside_bar")),
            inside_bar_count=(
                None
                if data.get("inside_bar_count") is None
                else _safe_int(data.get("inside_bar_count"))
            ),
            support_compression=_optional_bool(data.get("support_compression")),
            support_range_contraction_ratio=_optional_float(
                data.get("support_range_contraction_ratio")
            ),
            price_clustered_near_resistance=_optional_bool(
                data.get("price_clustered_near_resistance")
            ),
            resistance_cluster_test_count=(
                None
                if data.get("resistance_cluster_test_count") is None
                else _safe_int(data.get("resistance_cluster_test_count"))
            ),
            resistance_cluster_spread_pct=_optional_float(
                data.get("resistance_cluster_spread_pct")
            ),
            flat_base=_optional_bool(data.get("flat_base")),
            flat_base_depth_pct=_optional_float(data.get("flat_base_depth_pct")),
            ascending_triangle=_optional_bool(data.get("ascending_triangle")),
            darvas_consolidation=_optional_bool(
                data.get("darvas_consolidation")
            ),
            darvas_box_depth_pct=_optional_float(
                data.get("darvas_box_depth_pct")
            ),
            price_structure_reason_codes=[
                str(code)
                for code in (data.get("price_structure_reason_codes") or [])
            ],
            breakout_level=_optional_float(data.get("breakout_level")),
            distance_to_breakout_pct=_optional_float(
                data.get("distance_to_breakout_pct")
            ),
            pivot_source=(
                None
                if data.get("pivot_source") is None
                else str(data.get("pivot_source"))
            ),
            pivot_test_count=(
                None
                if data.get("pivot_test_count") is None
                else _safe_int(data.get("pivot_test_count"))
            ),
            pivot_quality_score=(
                None
                if data.get("pivot_quality_score") is None
                else _safe_int(data.get("pivot_quality_score"))
            ),
            near_pivot=_optional_bool(data.get("near_pivot")),
            already_above_pivot=_optional_bool(data.get("already_above_pivot")),
            resistance_too_far=_optional_bool(data.get("resistance_too_far")),
            resistance_clustered=_optional_bool(data.get("resistance_clustered")),
            pivot_candidate_count=_safe_int(data.get("pivot_candidate_count")),
            pivot_candidates=[
                dict(candidate) for candidate in (data.get("pivot_candidates") or [])
            ],
            pivot_reason_codes=[
                str(code) for code in (data.get("pivot_reason_codes") or [])
            ],
            pivot_quality_flags=[
                str(flag) for flag in (data.get("pivot_quality_flags") or [])
            ],
            base_duration_sessions=(
                None if data.get("base_duration_sessions") is None
                else _safe_int(data.get("base_duration_sessions"))
            ),
            base_depth_pct=_optional_float(data.get("base_depth_pct")),
            base_quality_score=(
                None if data.get("base_quality_score") is None
                else _safe_int(data.get("base_quality_score"))
            ),
            progressively_smaller_contractions=_optional_bool(
                data.get("progressively_smaller_contractions")
            ),
            overhead_resistance_pct=_optional_float(data.get("overhead_resistance_pct")),
            overhead_resistance_clear=_optional_bool(data.get("overhead_resistance_clear")),
            premature_breakout=_optional_bool(data.get("premature_breakout")),
            already_extended=_optional_bool(data.get("already_extended")),
            base_reason_codes=[str(code) for code in (data.get("base_reason_codes") or [])],
            base_risk_flags=[str(flag) for flag in (data.get("base_risk_flags") or [])],
            vcp_detected=_optional_bool(data.get("vcp_detected")),
            vcp_invalid=_optional_bool(data.get("vcp_invalid")),
            vcp_quality_score=(
                None
                if data.get("vcp_quality_score") is None
                else _safe_int(data.get("vcp_quality_score"))
            ),
            contraction_count=_safe_int(data.get("contraction_count")),
            contraction_depths=[
                _safe_float(depth) for depth in (data.get("contraction_depths") or [])
            ],
            contraction_durations=[
                _safe_int(duration)
                for duration in (data.get("contraction_durations") or [])
            ],
            depths_decreasing=_optional_bool(data.get("depths_decreasing")),
            t1_t2_t3_tightening=_optional_bool(
                data.get("t1_t2_t3_tightening")
            ),
            volatility_contracting=_optional_bool(
                data.get("volatility_contracting")
            ),
            volume_contracting=_optional_bool(data.get("volume_contracting")),
            tight_near_pivot=_optional_bool(data.get("tight_near_pivot")),
            higher_lows_present=_optional_bool(data.get("higher_lows_present")),
            independent_confirmation_count=_safe_int(
                data.get("independent_confirmation_count")
            ),
            vcp_reason_codes=[
                str(code) for code in (data.get("vcp_reason_codes") or [])
            ],
            vcp_risk_flags=[
                str(flag) for flag in (data.get("vcp_risk_flags") or [])
            ],
            vcp_data_quality=[
                str(flag) for flag in (data.get("vcp_data_quality") or [])
            ],
            demand_pressure_score=(
                None if data.get("demand_pressure_score") is None
                else _safe_int(data.get("demand_pressure_score"))
            ),
            supply_pressure_score=(
                None if data.get("supply_pressure_score") is None
                else _safe_int(data.get("supply_pressure_score"))
            ),
            accumulation_distribution_balance=_optional_float(
                data.get("accumulation_distribution_balance")
            ),
            pullback_volume_contracting=_optional_bool(
                data.get("pullback_volume_contracting")
            ),
            resistance_absorption_detected=_optional_bool(
                data.get("resistance_absorption_detected")
            ),
            selling_pressure_declining=_optional_bool(
                data.get("selling_pressure_declining")
            ),
            demand_expansion_detected=_optional_bool(
                data.get("demand_expansion_detected")
            ),
            price_progress_per_volume=_optional_float(
                data.get("price_progress_per_volume")
            ),
            supply_demand_reason_codes=[
                str(code) for code in (data.get("supply_demand_reason_codes") or [])
            ],
            supply_demand_risk_flags=[
                str(flag) for flag in (data.get("supply_demand_risk_flags") or [])
            ],
            overhead_supply_score=(
                None if data.get("overhead_supply_score") is None
                else _safe_int(data.get("overhead_supply_score"))
            ),
            overhead_supply_clear=_optional_bool(data.get("overhead_supply_clear")),
            nearest_overhead_resistance=_optional_float(
                data.get("nearest_overhead_resistance")
            ),
            distance_to_overhead_resistance_pct=_optional_float(
                data.get("distance_to_overhead_resistance_pct")
            ),
            overhead_resistance_count=(
                None if data.get("overhead_resistance_count") is None
                else _safe_int(data.get("overhead_resistance_count"))
            ),
            overhead_high_volume_zone_count=(
                None if data.get("overhead_high_volume_zone_count") is None
                else _safe_int(data.get("overhead_high_volume_zone_count"))
            ),
            overhead_supply_reason_codes=[
                str(code) for code in (data.get("overhead_supply_reason_codes") or [])
            ],
            overhead_supply_risk_flags=[
                str(flag) for flag in (data.get("overhead_supply_risk_flags") or [])
            ],
            failed_breakout_count=(
                None if data.get("failed_breakout_count") is None
                else _safe_int(data.get("failed_breakout_count"))
            ),
            recent_failed_breakout=_optional_bool(data.get("recent_failed_breakout")),
            days_since_failed_breakout=(
                None if data.get("days_since_failed_breakout") is None
                else _safe_int(data.get("days_since_failed_breakout"))
            ),
            same_zone_failure_count=(
                None if data.get("same_zone_failure_count") is None
                else _safe_int(data.get("same_zone_failure_count"))
            ),
            failure_severity=(
                None if data.get("failure_severity") is None
                else str(data.get("failure_severity"))
            ),
            failed_breakout_reason_codes=[
                str(code) for code in (data.get("failed_breakout_reason_codes") or [])
            ],
            failed_breakout_risk_flags=[
                str(flag) for flag in (data.get("failed_breakout_risk_flags") or [])
            ],
            setup_lifecycle=str(data.get("setup_lifecycle", "NO_SETUP")),
            setup_readiness_score=_safe_int(data.get("setup_readiness_score")),
            sector_context_status=str(
                data.get("sector_context_status", "SECTOR_CONTEXT_UNAVAILABLE")
            ),
            setup_reason_codes=[
                str(code) for code in (data.get("setup_reason_codes") or [])
            ],
            setup_risk_flags=[
                str(flag) for flag in (data.get("setup_risk_flags") or [])
            ],
            market_regime=(
                None
                if data.get("market_regime") is None
                else str(data.get("market_regime"))
            ),
            market_context_quality=(
                None
                if data.get("market_context_quality") is None
                else _safe_int(data.get("market_context_quality"))
            ),
            nifty_close=_optional_float(data.get("nifty_close")),
            nifty_ema_20=_optional_float(data.get("nifty_ema_20")),
            nifty_ema_50=_optional_float(data.get("nifty_ema_50")),
            nifty_sma_50=_optional_float(data.get("nifty_sma_50")),
            nifty_sma_200=_optional_float(data.get("nifty_sma_200")),
            nifty_above_20ema=_optional_bool(data.get("nifty_above_20ema")),
            nifty_above_50ema=_optional_bool(data.get("nifty_above_50ema")),
            nifty_above_50dma=_optional_bool(data.get("nifty_above_50dma")),
            nifty_above_200dma=_optional_bool(data.get("nifty_above_200dma")),
            nifty_50dma_above_200dma=_optional_bool(
                data.get("nifty_50dma_above_200dma")
            ),
            nifty_ema20_slope=_optional_float(data.get("nifty_ema20_slope")),
            nifty_ema50_slope=_optional_float(data.get("nifty_ema50_slope")),
            nifty_ma_slope=_optional_float(data.get("nifty_ma_slope")),
            nifty_sma200_slope=_optional_float(data.get("nifty_sma200_slope")),
            short_term_market_trend=(
                None
                if data.get("short_term_market_trend") is None
                else str(data.get("short_term_market_trend"))
            ),
            medium_term_market_trend=(
                None
                if data.get("medium_term_market_trend") is None
                else str(data.get("medium_term_market_trend"))
            ),
            long_term_market_trend=(
                None
                if data.get("long_term_market_trend") is None
                else str(data.get("long_term_market_trend"))
            ),
            nifty_rsi=_optional_float(data.get("nifty_rsi")),
            nifty_atr_pct=_optional_float(data.get("nifty_atr_pct")),
            market_volatility_regime=(
                None
                if data.get("market_volatility_regime") is None
                else str(data.get("market_volatility_regime"))
            ),
            nifty_distance_from_52w_high_pct=_optional_float(
                data.get("nifty_distance_from_52w_high_pct")
            ),
            nifty_recent_drawdown_pct=_optional_float(
                data.get("nifty_recent_drawdown_pct")
            ),
            market_reason_codes=[
                str(code) for code in (data.get("market_reason_codes") or [])
            ],
            market_risk_flags=[
                str(flag) for flag in (data.get("market_risk_flags") or [])
            ],
            market_data_quality=[
                str(flag) for flag in (data.get("market_data_quality") or [])
            ],

            donchian_upper=_safe_float(data.get("donchian_upper")),
            donchian_middle=_safe_float(data.get("donchian_middle")),
            donchian_lower=_safe_float(data.get("donchian_lower")),
            donchian_breakout=bool(data.get("donchian_breakout", False)),

            supertrend=_safe_float(data.get("supertrend")),
            supertrend_upper=_safe_float(data.get("supertrend_upper")),
            supertrend_lower=_safe_float(data.get("supertrend_lower")),

            resistance=_safe_float(data.get("resistance")),
            support=_safe_float(data.get("support")),
            distance_from_resistance=_safe_float(
                data.get("distance_from_resistance")
            ),
            resistance_tests=_safe_int(
                data.get("resistance_tests")
            ),
            consolidation_days=_safe_int(
                data.get("consolidation_days")
            ),
            breakout_probability=_safe_float(
                data.get("breakout_probability")
            ),
        )

    @property
    def change(self) -> float:
        return self.last_price - self.previous_close

    @property
    def change_percent(self) -> float:
        return _percent_change(self.last_price, self.previous_close)

    @property
    def is_liquid(self) -> bool:
        if self.avg_volume <= 0:
            return True
        return self.volume >= max(self.avg_volume * 0.6, 1)

    @property
    def near_52_week_high(self) -> bool:
        if self.week_52_high <= 0:
            return False
        distance = (self.week_52_high - self.last_price) / self.week_52_high * 100.0
        return distance <= 25.0

    @property
    def above_50_dma(self) -> bool:
        return self.dma_50 > 0 and self.last_price > self.dma_50

    @property
    def above_150_dma(self) -> bool:
        return self.dma_150 > 0 and self.last_price > self.dma_150

    @property
    def above_200_dma(self) -> bool:
        return self.dma_200 > 0 and self.last_price > self.dma_200

    @property
    def dma_150_above_200(self) -> bool:
        return self.dma_150 > 0 and self.dma_200 > 0 and self.dma_150 > self.dma_200

    @property
    def volume_surge(self) -> float:
        return _volume_surge(self.volume, self.avg_volume)

    @property
    def has_technical_base(self) -> bool:
        return _has_any(
            self.last_price,
            self.previous_close,
            self.open_price,
            self.high_price,
            self.low_price,
            self.dma_50,
            self.dma_150,
            self.dma_200,
            self.week_52_high,
            self.week_52_low,
        )

    @property
    def has_fundamental_base(self) -> bool:
        return _has_any(
            self.market_cap,
            self.pe_ratio,
            self.roe,
            self.roce,
            self.debt_to_equity,
            self.sales_growth,
            self.profit_growth,
            self.earnings_growth,
            self.cashflow_positive,
            self.institutional_holding_growth,
            self.sector_strength,
        )


@dataclass(slots=True)
class StrategyResult:
    strategy_name: str
    passed: bool
    score: int
    weight: int
    reasons: list[str] = field(default_factory=list)
    entry_zone: tuple[float, float] | None = None
    stop_loss: float | None = None
    targets: list[float] = field(default_factory=list)

    @property
    def confidence(self) -> int:
        return int(_clamp(self.score, 0, 100))


@dataclass(slots=True)
class ScanReport:
    snapshot: StockSnapshot
    strategies: list[StrategyResult]
    overall_score: int
    passed_count: int
    entry_zone: tuple[float, float] | None
    stop_loss: float | None
    targets: list[float]
    risk_reward: float
    should_alert: bool
    is_pre_breakout: bool
    is_breakout: bool
    breakout_probability: float
    resistance: float
    support: float
    distance_from_breakout: float
    confidence_score: float
    raw_prebreakout_score: int
    prebreakout_score: int
    prebreakout_classification: str
    component_scores: dict[str, dict[str, Any]]
    positive_signals: list[str]
    prebreakout_risk_flags: list[str]
    prebreakout_data_quality: list[str]
    prebreakout_applied_penalties: dict[str, int]
    prebreakout_applied_caps: list[str]

    entry_low: float | None = None
    entry_high: float | None = None
    strategy_name: str = ""

    @property
    def status(self) -> str:
        if self.should_alert:
            return "Entry Zone Active"
        if self.overall_score >= 80:
            return "Strong Candidate"
        if self.overall_score >= 70:
            return "Watchlist"
        return "Ignore"


class StrategyBase:
    name = "Base"
    weight = 10

    def applicable(self, snapshot: StockSnapshot) -> bool:
        return True

    def evaluate(self, snapshot: StockSnapshot) -> StrategyResult:
        raise NotImplementedError

    def _weighted_score(self, flags: list[tuple[bool, int]]) -> int:
        total = sum(weight for _, weight in flags)
        if total <= 0:
            return 0
        achieved = sum(weight for passed, weight in flags if passed)
        return int(round((achieved / total) * 100))

    def _entry_zone(self, snapshot: StockSnapshot, cushion_pct: float = 1.5) -> tuple[float, float]:
        base = snapshot.last_price if snapshot.last_price > 0 else snapshot.previous_close
        low = base * (1.0 - cushion_pct / 100.0)
        high = base * (1.0 + cushion_pct / 100.0)
        return (round(low, 2), round(high, 2))

    def _targets_from_rr(self, snapshot: StockSnapshot, stop_loss: float, rr_multipliers: list[float]) -> list[float]:
        risk = max(snapshot.last_price - stop_loss, 0.0)
        if risk <= 0:
            return []
        return [round(snapshot.last_price + (risk * mult), 2) for mult in rr_multipliers]

    def _inactive_result(self, reason: str) -> StrategyResult:
        return StrategyResult(
            strategy_name=self.name,
            passed=False,
            score=0,
            weight=0,
            reasons=[reason],
            entry_zone=None,
            stop_loss=None,
            targets=[],
        )


class MinerviniStrategy(StrategyBase):
    name = "Minervini"
    weight = 25

    def evaluate(self, snapshot: StockSnapshot) -> StrategyResult:
        flags = [
            (snapshot.above_50_dma, 10),
            (snapshot.above_150_dma, 15),
            (snapshot.above_200_dma, 15),
            (snapshot.dma_150_above_200, 10),
            (snapshot.near_52_week_high, 15),
            (snapshot.relative_strength >= 80, 15),
            (snapshot.volume_surge >= 1.2, 20),
        ]
        score = self._weighted_score(flags)
        passed = (
            snapshot.above_50_dma
            and snapshot.above_150_dma
            and snapshot.above_200_dma
            and snapshot.dma_150_above_200
            and snapshot.near_52_week_high
            and snapshot.relative_strength >= 80
        )

        reasons: list[str] = []
        if snapshot.above_50_dma:
            reasons.append("Price above 50 DMA")
        if snapshot.above_150_dma:
            reasons.append("Price above 150 DMA")
        if snapshot.above_200_dma:
            reasons.append("Price above 200 DMA")
        if snapshot.dma_150_above_200:
            reasons.append("150 DMA above 200 DMA")
        if snapshot.near_52_week_high:
            reasons.append("Near 52-week high")
        if snapshot.relative_strength >= 80:
            reasons.append("Relative strength strong")
        if snapshot.volume_surge >= 1.2:
            reasons.append("Volume surge confirmed")

        stop_loss = round(min(snapshot.dma_50 or snapshot.last_price * 0.97, snapshot.last_price * 0.96), 2)
        targets = self._targets_from_rr(snapshot, stop_loss, [1.0, 1.8, 2.6])

        return StrategyResult(
            strategy_name=self.name,
            passed=passed,
            score=score,
            weight=self.weight,
            reasons=reasons,
            entry_zone=self._entry_zone(snapshot, 1.8),
            stop_loss=stop_loss,
            targets=targets,
        )


class CanSlimStrategy(StrategyBase):
    name = "CANSLIM"
    weight = 20

    def applicable(self, snapshot: StockSnapshot) -> bool:
        return snapshot.has_fundamental_base or _has_any(
            snapshot.sales_growth,
            snapshot.profit_growth,
            snapshot.earnings_growth,
            snapshot.sector_strength,
        )

    def evaluate(self, snapshot: StockSnapshot) -> StrategyResult:
        if not self.applicable(snapshot):
            return self._inactive_result("Insufficient fundamental data for CANSLIM")

        flags = [
            (snapshot.sales_growth >= 25, 20),
            (snapshot.profit_growth >= 25, 20),
            (snapshot.relative_strength >= 80, 20),
            (snapshot.above_50_dma, 10),
            (snapshot.above_200_dma, 10),
            (snapshot.volume_surge >= 1.4, 10),
            (snapshot.sector_strength >= 70 or snapshot.sector_strength == 0, 10),
        ]
        score = self._weighted_score(flags)
        passed = (
            snapshot.sales_growth >= 25
            and snapshot.profit_growth >= 25
            and snapshot.relative_strength >= 80
            and snapshot.above_50_dma
            and snapshot.above_200_dma
        )

        reasons: list[str] = []
        if snapshot.sales_growth >= 25:
            reasons.append("Sales growth strong")
        if snapshot.profit_growth >= 25:
            reasons.append("Profit growth strong")
        if snapshot.relative_strength >= 80:
            reasons.append("Relative strength strong")
        if snapshot.above_50_dma:
            reasons.append("Price above 50 DMA")
        if snapshot.above_200_dma:
            reasons.append("Price above 200 DMA")
        if snapshot.volume_surge >= 1.4:
            reasons.append("Breakout volume confirmed")

        stop_loss = round(min(snapshot.dma_50 or snapshot.last_price * 0.97, snapshot.last_price * 0.95), 2)
        targets = self._targets_from_rr(snapshot, stop_loss, [1.0, 2.0, 3.0])

        return StrategyResult(
            strategy_name=self.name,
            passed=passed,
            score=score,
            weight=self.weight,
            reasons=reasons,
            entry_zone=self._entry_zone(snapshot, 2.0),
            stop_loss=stop_loss,
            targets=targets,
        )


class DarvasStrategy(StrategyBase):
    name = "Darvas"
    weight = 15

    def evaluate(self, snapshot: StockSnapshot) -> StrategyResult:
        flags = [
            (snapshot.last_price >= snapshot.open_price if snapshot.open_price > 0 else True, 10),
            (snapshot.last_price >= snapshot.high_price * 0.98 if snapshot.high_price > 0 else True, 15),
            (snapshot.near_52_week_high, 20),
            (snapshot.volume_surge >= 1.1, 15),
            (snapshot.above_50_dma, 15),
            (snapshot.relative_strength >= 70, 10),
            (snapshot.change >= 0, 15),
        ]
        score = self._weighted_score(flags)
        passed = (
            snapshot.near_52_week_high
            and snapshot.volume_surge >= 1.1
            and snapshot.above_50_dma
            and snapshot.change >= 0
        )

        reasons: list[str] = []
        if snapshot.near_52_week_high:
            reasons.append("Near high / breakout zone")
        if snapshot.volume_surge >= 1.1:
            reasons.append("Volume expansion")
        if snapshot.above_50_dma:
            reasons.append("Above 50 DMA")
        if snapshot.change >= 0:
            reasons.append("Positive momentum")

        stop_loss = round(min(snapshot.dma_50 or snapshot.last_price * 0.96, snapshot.last_price * 0.94), 2)
        targets = self._targets_from_rr(snapshot, stop_loss, [0.9, 1.6, 2.4])

        return StrategyResult(
            strategy_name=self.name,
            passed=passed,
            score=score,
            weight=self.weight,
            reasons=reasons,
            entry_zone=self._entry_zone(snapshot, 1.2),
            stop_loss=stop_loss,
            targets=targets,
        )


class LynchGrowthStrategy(StrategyBase):
    name = "Lynch"
    weight = 10

    def applicable(self, snapshot: StockSnapshot) -> bool:
        return snapshot.has_fundamental_base or _has_any(
            snapshot.pe_ratio,
            snapshot.roe,
            snapshot.roce,
            snapshot.debt_to_equity,
            snapshot.sales_growth,
            snapshot.profit_growth,
            snapshot.earnings_growth,
        )

    def evaluate(self, snapshot: StockSnapshot) -> StrategyResult:
        if not self.applicable(snapshot):
            return self._inactive_result("Insufficient fundamental data for Lynch")

        pe_ok = 0 < snapshot.pe_ratio <= 30
        roe_ok = snapshot.roe >= 15
        growth_ok = snapshot.profit_growth >= 15 or snapshot.sales_growth >= 15
        debt_ok = snapshot.debt_to_equity <= 1.5 or snapshot.debt_to_equity == 0
        price_momentum = snapshot.above_50_dma or snapshot.change >= 0

        flags = [
            (pe_ok, 20),
            (roe_ok, 25),
            (growth_ok, 25),
            (debt_ok, 15),
            (price_momentum, 15),
        ]
        score = self._weighted_score(flags)
        passed = pe_ok and roe_ok and growth_ok and debt_ok

        reasons: list[str] = []
        if pe_ok:
            reasons.append("Reasonable valuation")
        if roe_ok:
            reasons.append("ROE healthy")
        if growth_ok:
            reasons.append("Growth visible")
        if debt_ok:
            reasons.append("Balance sheet acceptable")

        stop_loss = round(snapshot.last_price * 0.95, 2)
        targets = self._targets_from_rr(snapshot, stop_loss, [0.8, 1.4, 2.0])

        return StrategyResult(
            strategy_name=self.name,
            passed=passed,
            score=score,
            weight=self.weight,
            reasons=reasons,
            entry_zone=self._entry_zone(snapshot, 2.5),
            stop_loss=stop_loss,
            targets=targets,
        )


class BuffettQualityStrategy(StrategyBase):
    name = "Buffett"
    weight = 10

    def applicable(self, snapshot: StockSnapshot) -> bool:
        return snapshot.has_fundamental_base or _has_any(
            snapshot.cashflow_positive,
            snapshot.roe,
            snapshot.roce,
            snapshot.debt_to_equity,
            snapshot.pe_ratio,
            snapshot.earnings_growth,
        )

    def evaluate(self, snapshot: StockSnapshot) -> StrategyResult:
        if not self.applicable(snapshot):
            return self._inactive_result("Insufficient fundamental data for Buffett")

        cashflow_ok = snapshot.cashflow_positive
        roe_ok = snapshot.roe >= 15
        roce_ok = snapshot.roce >= 15
        debt_ok = snapshot.debt_to_equity <= 1.0 or snapshot.debt_to_equity == 0
        earnings_ok = snapshot.earnings_growth >= 10 or snapshot.profit_growth >= 10
        valuation_ok = 0 < snapshot.pe_ratio <= 35

        flags = [
            (cashflow_ok, 25),
            (roe_ok, 20),
            (roce_ok, 20),
            (debt_ok, 15),
            (earnings_ok, 10),
            (valuation_ok, 10),
        ]
        score = self._weighted_score(flags)
        passed = cashflow_ok and roe_ok and roce_ok and debt_ok

        reasons: list[str] = []
        if cashflow_ok:
            reasons.append("Cash flow positive")
        if roe_ok:
            reasons.append("ROE strong")
        if roce_ok:
            reasons.append("ROCE strong")
        if debt_ok:
            reasons.append("Debt manageable")
        if earnings_ok:
            reasons.append("Earnings growth positive")
        if valuation_ok:
            reasons.append("Valuation acceptable")

        stop_loss = round(snapshot.last_price * 0.93, 2)
        targets = self._targets_from_rr(snapshot, stop_loss, [0.7, 1.2, 1.8])

        return StrategyResult(
            strategy_name=self.name,
            passed=passed,
            score=score,
            weight=self.weight,
            reasons=reasons,
            entry_zone=self._entry_zone(snapshot, 3.0),
            stop_loss=stop_loss,
            targets=targets,
        )


class DonchianBreakoutStrategy(StrategyBase):
    name = "Donchian"
    weight = 10

    def evaluate(self, snapshot: StockSnapshot) -> StrategyResult:
        breakout = snapshot.last_price >= max(snapshot.high_price, snapshot.week_52_high * 0.98 if snapshot.week_52_high else 0)
        momentum = snapshot.volume_surge >= 1.25
        trend = snapshot.above_50_dma or snapshot.above_200_dma

        flags = [
            (breakout, 40),
            (momentum, 30),
            (trend, 20),
            (snapshot.change >= 0, 10),
        ]
        score = self._weighted_score(flags)
        passed = breakout and momentum and trend

        reasons: list[str] = []
        if breakout:
            reasons.append("Breakout level hit")
        if momentum:
            reasons.append("Volume supports breakout")
        if trend:
            reasons.append("Trend support present")

        stop_loss = round(snapshot.last_price * 0.94, 2)
        targets = self._targets_from_rr(snapshot, stop_loss, [1.0, 1.8, 2.8])

        return StrategyResult(
            strategy_name=self.name,
            passed=passed,
            score=score,
            weight=self.weight,
            reasons=reasons,
            entry_zone=self._entry_zone(snapshot, 1.0),
            stop_loss=stop_loss,
            targets=targets,
        )


class EMACrossoverStrategy(StrategyBase):
    name = "EMA"
    weight = 5

    def evaluate(self, snapshot: StockSnapshot) -> StrategyResult:
        ema_fast = snapshot.dma_50
        ema_slow = snapshot.dma_200

        bullish = ema_fast > 0 and ema_slow > 0 and ema_fast > ema_slow and snapshot.last_price > ema_fast
        flags = [
            (bullish, 60),
            (snapshot.change >= 0, 20),
            (snapshot.volume_surge >= 1.0, 20),
        ]
        score = self._weighted_score(flags)
        passed = bullish

        reasons: list[str] = []
        if bullish:
            reasons.append("EMA trend bullish")
        if snapshot.change >= 0:
            reasons.append("Price positive")
        if snapshot.volume_surge >= 1.0:
            reasons.append("Liquidity supportive")

        stop_loss = round(snapshot.last_price * 0.95, 2)
        targets = self._targets_from_rr(snapshot, stop_loss, [0.8, 1.5, 2.1])

        return StrategyResult(
            strategy_name=self.name,
            passed=passed,
            score=score,
            weight=self.weight,
            reasons=reasons,
            entry_zone=self._entry_zone(snapshot, 1.2),
            stop_loss=stop_loss,
            targets=targets,
        )


class RSIStrategy(StrategyBase):
    name = "RSI"
    weight = 5

    def evaluate(self, snapshot: StockSnapshot) -> StrategyResult:
        rsi = _safe_float(getattr(snapshot, "rsi", 0.0))
        bullish = 50 <= rsi <= 70 if rsi > 0 else snapshot.change >= 0 and snapshot.volume_surge >= 1.0

        flags = [
            (bullish, 70),
            (snapshot.change >= 0, 15),
            (snapshot.volume_surge >= 1.0, 15),
        ]
        score = self._weighted_score(flags)
        passed = bullish

        reasons: list[str] = []
        if rsi > 0:
            reasons.append(f"RSI {rsi:.1f}")
        elif bullish:
            reasons.append("Momentum positive")
        if snapshot.change >= 0:
            reasons.append("Price up")
        if snapshot.volume_surge >= 1.0:
            reasons.append("Volume normal/strong")

        stop_loss = round(snapshot.last_price * 0.96, 2)
        targets = self._targets_from_rr(snapshot, stop_loss, [0.8, 1.3, 1.9])

        return StrategyResult(
            strategy_name=self.name,
            passed=passed,
            score=score,
            weight=self.weight,
            reasons=reasons,
            entry_zone=self._entry_zone(snapshot, 1.0),
            stop_loss=stop_loss,
            targets=targets,
        )


class ScannerEngine:

    def __init__(
        self,
        *,
        alert_threshold: int = 90,
        min_passed_strategies: int = 3,
        min_risk_reward: float = 2.0,
    ):
        self.alert_threshold = alert_threshold
        self.min_passed_strategies = min_passed_strategies
        self.min_risk_reward = min_risk_reward

        self.strategies: list[StrategyBase] = [
            MinerviniStrategy(),
            CanSlimStrategy(),
            DarvasStrategy(),
            LynchGrowthStrategy(),
            BuffettQualityStrategy(),
            DonchianBreakoutStrategy(),
            EMACrossoverStrategy(),
            RSIStrategy(),
        ]

    def enrich_market_data(
        self,
        df: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Enrich OHLCV data with all technical indicators.
        """

        return indicator_engine.calculate(df)

    def scan(
        self,
        snapshot: StockSnapshot | Mapping[str, Any],
    ) -> ScanReport: 

        if not isinstance(snapshot, StockSnapshot):
            snapshot = StockSnapshot.from_mapping(snapshot)

        results = [strategy.evaluate(snapshot) for strategy in self.strategies]
        pre = prebreakout_engine.analyze(snapshot)
        applicable = [result for result in results if result.weight > 0]

        if not applicable:
            applicable = results

        total_weight = sum(result.weight for result in applicable) or 1
        overall_score = int(
            round(
                sum(result.score * result.weight for result in applicable) / total_weight
            )
        )

        passed_count = sum(1 for result in applicable if result.passed)
        best_result = max(applicable, key=lambda r: (r.score, r.weight), default=None)

        entry_zone = best_result.entry_zone if best_result and best_result.entry_zone else None
        stop_loss = best_result.stop_loss if best_result and best_result.stop_loss else None
        targets = best_result.targets if best_result and best_result.targets else []

        risk_reward = self._risk_reward(snapshot.last_price, stop_loss, targets)
        should_alert = (
            overall_score >= self.alert_threshold
            and passed_count >= self.min_passed_strategies
            and risk_reward >= self.min_risk_reward
            and snapshot.is_liquid
        )

        return ScanReport(
            snapshot=snapshot,
            strategies=results,
            overall_score=overall_score,
            passed_count=passed_count,

            entry_zone=entry_zone,
            entry_low=pre["entry_low"],
            entry_high=pre["entry_high"],

            stop_loss=stop_loss,
            targets=targets,
            risk_reward=risk_reward,

            should_alert=should_alert,

            strategy_name=(
               ", ".join(
                    result.strategy_name
                    for result in sorted(
                        applicable,
                        key=lambda x: (x.score, x.weight),
                        reverse=True,
                    )
                    if result.passed
                )
                or (
                    best_result.strategy_name
                    if best_result
                    else "Pre Breakout"
                 )
            ),

            is_pre_breakout=pre["pre_breakout"],
            is_breakout=pre["breakout"],

            breakout_probability=pre["breakout_probability"],

            resistance=pre["resistance"],
            support=pre["support"],

            distance_from_breakout=pre["distance_from_breakout"],

            confidence_score=pre["confidence"],
            raw_prebreakout_score=pre["raw_prebreakout_score"],
            prebreakout_score=pre["prebreakout_score"],
            prebreakout_classification=pre["classification"],
            component_scores=pre["component_scores"],
            positive_signals=pre["positive_signals"],
            prebreakout_risk_flags=pre["risk_flags"],
            prebreakout_data_quality=pre["data_quality"],
            prebreakout_applied_penalties=pre["applied_penalties"],
            prebreakout_applied_caps=pre["applied_caps"],
        )

    def scan_many(self, snapshots: Iterable[StockSnapshot | Mapping[str, Any]]) -> list[ScanReport]:
        reports = [self.scan(snapshot) for snapshot in snapshots]
        reports.sort(key=lambda report: (report.overall_score, report.passed_count), reverse=True)
        return reports

    def filter_alerts(self, snapshots: Iterable[StockSnapshot | Mapping[str, Any]]) -> list[ScanReport]:
        return [report for report in self.scan_many(snapshots) if report.should_alert]

    def _risk_reward(self, entry_price: float, stop_loss: float | None, targets: list[float]) -> float:
        if not stop_loss or entry_price <= 0 or stop_loss >= entry_price:
            return 0.0
        if not targets:
            return 0.0
        risk = entry_price - stop_loss
        reward = max(targets) - entry_price
        if risk <= 0:
            return 0.0
        return round(reward / risk, 2)

    def build_payload(self, report: ScanReport) -> dict[str, Any]:
        stock = report.snapshot
        strategy_cards = [
            {
                "name": result.strategy_name,
                "score": result.score,
                "passed": result.passed,
                "weight": result.weight,
                "reasons": result.reasons,
            }
            for result in sorted(report.strategies, key=lambda r: (r.score, r.weight), reverse=True)
        ]

        return {
            "symbol": stock.symbol,
            "company_name": stock.company_name,
            "sector": stock.sector,
            "industry": stock.industry,
            "exchange": stock.exchange,
            "price": round(stock.last_price, 2),
            "overall_score": report.overall_score,
            "status": report.status,
            "entry_zone": report.entry_zone,
            "entry_low": report.entry_zone[0] if report.entry_zone else None,
            "entry_high": report.entry_zone[1] if report.entry_zone else None,
            "stop_loss": report.stop_loss,
            "targets": report.targets,
            "risk_reward": report.risk_reward,
            "passed_strategies": report.passed_count,
            "strategies": strategy_cards,
            "should_alert": report.should_alert,
            "updated_at": stock.timestamp.isoformat() if stock.timestamp else None,
            "pre_breakout": report.is_pre_breakout,
            "breakout": report.is_breakout,
            "confidence_score": report.confidence_score,
            "breakout_probability": report.breakout_probability,
            "resistance": report.resistance,
            "support": report.support,
            "distance_from_breakout": report.distance_from_breakout,
        }

    def build_telegram_message(self, report: ScanReport) -> str:
        stock = report.snapshot
        strategies = sorted(report.strategies, key=lambda r: (r.score, r.weight), reverse=True)

        lines = [
            "🚨 QuantumStock AI",
            "",
            f"🔥 {report.status.upper()}",
            "",
            f"Stock: {stock.symbol}",
            f"Company: {stock.company_name or stock.symbol}",
            f"Price: ₹{stock.last_price:,.2f}",
            f"Overall Score: {report.overall_score}/100",
            "",
            "Top Strategies:",
        ]

        for result in strategies[:5]:
            mark = "✅" if result.passed else "•"
            lines.append(f"{mark} {result.strategy_name} {result.score}/100")

        if report.entry_zone:
            lines.extend(
                [
                    "",
                    f"Entry Zone: ₹{report.entry_zone[0]:,.2f} - ₹{report.entry_zone[1]:,.2f}",
                ]
            )

        if report.stop_loss:
            lines.append(f"Stop Loss: ₹{report.stop_loss:,.2f}")

        if report.targets:
            lines.append("Targets:")
            for target in report.targets[:3]:
                lines.append(f"₹{target:,.2f}")

        lines.extend(
            [
                "",
                f"Risk Reward: 1 : {report.risk_reward:.2f}",
                f"Passed Strategies: {report.passed_count}",
                "",
                "Open QuantumStock AI for full analysis.",
            ]
        )

        return "\n".join(lines)

    def build_email_subject(self, report: ScanReport) -> str:
        prefix = "🔥" if report.should_alert else "QuantumStock AI"
        return f"{prefix} {report.snapshot.symbol} - {report.status} ({report.overall_score}/100)"

    def build_email_body(self, report: ScanReport) -> str:
        stock = report.snapshot
        lines = [
            "Hello,",
            "",
            "A new setup has been detected in QuantumStock AI.",
            "",
            f"Stock: {stock.symbol}",
            f"Company: {stock.company_name or stock.symbol}",
            f"Price: ₹{stock.last_price:,.2f}",
            f"Overall Score: {report.overall_score}/100",
            f"Status: {report.status}",
            "",
            "Strategy Breakdown:",
        ]

        for result in sorted(report.strategies, key=lambda r: (r.score, r.weight), reverse=True):
            lines.append(f"- {result.strategy_name}: {result.score}/100 {'(PASS)' if result.passed else ''}")

        if report.entry_zone:
            lines.append("")
            lines.append(f"Entry Zone: ₹{report.entry_zone[0]:,.2f} - ₹{report.entry_zone[1]:,.2f}")

        if report.stop_loss:
            lines.append(f"Stop Loss: ₹{report.stop_loss:,.2f}")

        if report.targets:
            lines.append("Targets:")
            for target in report.targets[:3]:
                lines.append(f"- ₹{target:,.2f}")

        lines.extend(
            [
                "",
                f"Risk Reward: 1 : {report.risk_reward:.2f}",
                "",
                "Please review the setup inside QuantumStock AI before taking any action.",
            ]
        )

        return "\n".join(lines)


scanner_engine = ScannerEngine()
