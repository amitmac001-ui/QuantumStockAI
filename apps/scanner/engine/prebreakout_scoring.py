from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any

from .prebreakout_config import (
    CLASSIFICATION_SCORE_CAPS,
    COMPONENT_WEIGHTS,
    MARKET_CONTEXT_QUALITY_POINTS,
    MARKET_REGIME_BASE_POINTS,
    MOMENTUM_SCORE_POINTS,
    PIVOT_MIN_RESISTANCE_TESTS,
    PIVOT_SCORE_POINTS,
    RISK_PENALTIES,
    RS_SCORE_POINTS,
    SCORING_COMPONENT_CONFLUENCE_RATIO,
    SCORING_HEALTHY_ADX_MIN,
    SCORING_HEALTHY_RSI_MAX,
    SCORING_HEALTHY_RSI_MIN,
    SCORING_HIGH_QUALITY_MIN_AVAILABLE_COMPONENTS,
    SCORING_HIGH_QUALITY_MIN_CONFLUENT_COMPONENTS,
    SCORING_PRICE_EXTENSION_MIN_PERCENT,
    SCORING_RSI_EXTENDED_MIN,
    SCORING_STRONG_MIN_AVAILABLE_COMPONENTS,
    SCORING_STRONG_MIN_CONFLUENT_COMPONENTS,
    SCORING_WEAK_RS_RATING_MAX,
    TREND_SCORE_POINTS,
    VCP_EXPANDING_VOLATILITY_MIN_RATIO,
    VOLATILITY_SCORE_POINTS,
    VOLUME_SCORE_POINTS,
    classify_score,
    normalize_score,
)

if TYPE_CHECKING:
    from .decision_engine import StockSnapshot


@dataclass(slots=True)
class ComponentScore:
    component_score: int
    max_component_score: int
    supporting_reason_codes: list[str] = field(default_factory=list)
    available: bool = True
    data_quality: list[str] = field(default_factory=list)

    def as_mapping(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PreBreakoutScoreResult:
    raw_prebreakout_score: int
    prebreakout_score: int
    classification: str
    component_scores: dict[str, dict[str, Any]]
    positive_signals: list[str]
    risk_flags: list[str]
    data_quality: list[str]
    applied_penalties: dict[str, int]
    applied_caps: list[str]

    def as_mapping(self) -> dict[str, Any]:
        return asdict(self)


class PreBreakoutScorer:
    @staticmethod
    def _component(
        name: str,
        available: bool,
        score: int,
        reasons: list[str],
        quality: list[str] | None = None,
    ) -> ComponentScore:
        maximum = COMPONENT_WEIGHTS[name]
        return ComponentScore(
            component_score=max(0, min(maximum, int(round(score)))) if available else 0,
            max_component_score=maximum,
            supporting_reason_codes=list(dict.fromkeys(reasons)),
            available=available,
            data_quality=list(dict.fromkeys(quality or ([] if available else [f"{name.upper()}_UNAVAILABLE"]))),
        )

    @staticmethod
    def _fixed_signals(
        snapshot: StockSnapshot,
        points: dict[str, int] | Any,
        aliases: dict[str, str] | None = None,
    ) -> tuple[int, list[str]]:
        aliases = aliases or {}
        score = 0
        reasons = []
        for field_name, point_value in points.items():
            if getattr(snapshot, field_name, None) is True:
                score += point_value
                reasons.append(aliases.get(field_name, field_name.upper()))
        return score, reasons

    @staticmethod
    def _scaled(value: float | int | None, maximum: int) -> int:
        if value is None:
            return 0
        return int(round(max(0.0, min(float(value), 100.0)) / 100 * maximum))

    @classmethod
    def _trend(cls, snapshot: StockSnapshot) -> ComponentScore:
        available = any(
            getattr(snapshot, field_name, None) is not None
            for field_name in TREND_SCORE_POINTS
        )
        score, reasons = cls._fixed_signals(snapshot, TREND_SCORE_POINTS)
        return cls._component("trend", available, score, reasons)

    @classmethod
    def _volatility_vcp(cls, snapshot: StockSnapshot) -> ComponentScore:
        fixed = {
            key: value
            for key, value in VOLATILITY_SCORE_POINTS.items()
            if key not in {"narrow_range", "vcp_quality"}
        }
        available = any(getattr(snapshot, key, None) is not None for key in fixed) or (
            snapshot.vcp_quality_score is not None
        )
        score, reasons = cls._fixed_signals(snapshot, fixed)
        if snapshot.nr4 is True or snapshot.nr7 is True:
            score += VOLATILITY_SCORE_POINTS["narrow_range"]
            reasons.append("NARROW_RANGE_SESSION")
        vcp_points = (
            cls._scaled(
                snapshot.vcp_quality_score,
                VOLATILITY_SCORE_POINTS["vcp_quality"],
            )
            if snapshot.vcp_detected is True and snapshot.vcp_invalid is not True
            else 0
        )
        if vcp_points:
            score += vcp_points
            reasons.append("VCP_QUALITY")
        return cls._component("volatility_vcp", available, score, reasons)

    @classmethod
    def _volume(cls, snapshot: StockSnapshot) -> ComponentScore:
        available = any(
            getattr(snapshot, field_name, None) is not None
            for field_name in VOLUME_SCORE_POINTS
        )
        score, reasons = cls._fixed_signals(snapshot, VOLUME_SCORE_POINTS)
        return cls._component("volume", available, score, reasons)

    @classmethod
    def _relative_strength(cls, snapshot: StockSnapshot) -> ComponentScore:
        available = snapshot.rs_rating is not None and any(
            value is not None
            for value in (
                snapshot.rs_1m_pct,
                snapshot.rs_3m_pct,
                snapshot.rs_6m_pct,
                snapshot.rs_12m_pct,
            )
        )
        score = 0
        reasons = []
        horizons = (
            ("rs_1m_pct", "rs_1m_positive"),
            ("rs_3m_pct", "rs_3m_positive"),
            ("rs_6m_pct", "rs_6m_positive"),
            ("rs_12m_pct", "rs_12m_positive"),
        )
        for field_name, point_key in horizons:
            value = getattr(snapshot, field_name)
            if value is not None and value > 0:
                score += RS_SCORE_POINTS[point_key]
                reasons.append(point_key.upper())
        if snapshot.rs_improving is True:
            score += RS_SCORE_POINTS["rs_improving"]
            reasons.append("RS_IMPROVING")
        rating_points = cls._scaled(snapshot.rs_rating, RS_SCORE_POINTS["rs_rating"])
        if rating_points:
            score += rating_points
            reasons.append("RS_RATING")
        if snapshot.rs_new_high is True:
            score += RS_SCORE_POINTS["rs_new_high"]
            reasons.append("RS_NEW_HIGH")
        return cls._component("relative_strength", available, score, reasons)

    @classmethod
    def _pivot(cls, snapshot: StockSnapshot) -> ComponentScore:
        available = snapshot.breakout_level is not None and snapshot.pivot_quality_score is not None
        score = cls._scaled(
            snapshot.pivot_quality_score, PIVOT_SCORE_POINTS["pivot_quality"]
        )
        reasons = ["PIVOT_QUALITY"] if score else []
        if (
            snapshot.pivot_test_count is not None
            and snapshot.pivot_test_count >= PIVOT_MIN_RESISTANCE_TESTS
        ):
            score += PIVOT_SCORE_POINTS["repeated_tests"]
            reasons.append("REPEATED_RESISTANCE_TESTS")
        if snapshot.near_pivot is True and snapshot.already_above_pivot is not True:
            score += PIVOT_SCORE_POINTS["near_pivot"]
            reasons.append("NEAR_PIVOT")
        return cls._component("pivot", available, score, reasons)

    @classmethod
    def _momentum(cls, snapshot: StockSnapshot) -> ComponentScore:
        available = snapshot.rsi_slope is not None or snapshot.positive_directional_momentum is not None
        score = 0
        reasons = []
        if SCORING_HEALTHY_RSI_MIN <= snapshot.rsi <= SCORING_HEALTHY_RSI_MAX:
            score += MOMENTUM_SCORE_POINTS["healthy_rsi"]
            reasons.append("HEALTHY_RSI")
        if snapshot.rsi_slope is not None and snapshot.rsi_slope > 0:
            score += MOMENTUM_SCORE_POINTS["positive_rsi_slope"]
            reasons.append("POSITIVE_RSI_SLOPE")
        if snapshot.rsi_50_reclaim is True or snapshot.rsi_60_strength is True:
            score += MOMENTUM_SCORE_POINTS["rsi_reclaim_or_strength"]
            reasons.append("RSI_RECLAIM_OR_STRENGTH")
        if snapshot.macd_histogram_trend == "RISING":
            score += MOMENTUM_SCORE_POINTS["rising_macd_histogram"]
            reasons.append("RISING_MACD_HISTOGRAM")
        if snapshot.macd_histogram_expanding is True and snapshot.macd_histogram > 0:
            score += MOMENTUM_SCORE_POINTS["expanding_macd_histogram"]
            reasons.append("EXPANDING_POSITIVE_MACD_HISTOGRAM")
        if snapshot.positive_directional_momentum is True:
            score += MOMENTUM_SCORE_POINTS["positive_directional_momentum"]
            reasons.append("POSITIVE_DIRECTIONAL_MOMENTUM")
        if snapshot.adx >= SCORING_HEALTHY_ADX_MIN:
            score += MOMENTUM_SCORE_POINTS["healthy_adx"]
            reasons.append("HEALTHY_ADX")
        return cls._component("momentum", available, score, reasons)

    @classmethod
    def _market_context(cls, snapshot: StockSnapshot) -> ComponentScore:
        available = snapshot.market_regime in MARKET_REGIME_BASE_POINTS
        score = MARKET_REGIME_BASE_POINTS.get(snapshot.market_regime or "", 0)
        reasons = [f"MARKET_{snapshot.market_regime}"] if available else []
        quality_points = cls._scaled(
            snapshot.market_context_quality, MARKET_CONTEXT_QUALITY_POINTS
        )
        score += quality_points
        if quality_points:
            reasons.append("MARKET_CONTEXT_QUALITY")
        return cls._component("market_context", available, score, reasons)

    @staticmethod
    def _has_quality_flag(snapshot: StockSnapshot, token: str) -> bool:
        flags = [
            *snapshot.data_quality,
            *snapshot.vcp_data_quality,
            *snapshot.market_data_quality,
        ]
        return any(token in flag for flag in flags)

    @classmethod
    def score(cls, snapshot: StockSnapshot) -> PreBreakoutScoreResult:
        components = {
            "trend": cls._trend(snapshot),
            "volatility_vcp": cls._volatility_vcp(snapshot),
            "volume": cls._volume(snapshot),
            "relative_strength": cls._relative_strength(snapshot),
            "pivot": cls._pivot(snapshot),
            "momentum": cls._momentum(snapshot),
            "market_context": cls._market_context(snapshot),
        }
        raw_score = normalize_score(
            sum(component.component_score for component in components.values())
        )

        stale = cls._has_quality_flag(snapshot, "STALE_MARKET_DATA")
        quality_state = str(snapshot.data_quality_state or "INVALID").upper()
        quality_risk_flags = (
            [] if quality_state == "FRESH"
            else [f"DATA_QUALITY_{quality_state}"]
        )
        insufficient = cls._has_quality_flag(snapshot, "INSUFFICIENT")
        expanding_volatility = (
            "EXPANDING_VOLATILITY" in snapshot.vcp_risk_flags
            or any(
                ratio is not None and ratio >= VCP_EXPANDING_VOLATILITY_MIN_RATIO
                for ratio in (
                    snapshot.atr_contraction_ratio,
                    snapshot.rolling_range_contraction_ratio,
                    snapshot.candle_range_contraction_ratio,
                    snapshot.stddev_contraction_ratio,
                )
            )
        )
        distribution = "HEAVY_DISTRIBUTION" in snapshot.vcp_risk_flags or bool(
            snapshot.distribution_days is not None
            and snapshot.accumulation_days is not None
            and snapshot.distribution_days > snapshot.accumulation_days
            and snapshot.down_volume is not None
            and snapshot.up_volume is not None
            and snapshot.down_volume > snapshot.up_volume
        )
        price_extended = bool(
            snapshot.already_above_pivot is True
            and snapshot.distance_to_breakout_pct is not None
            and snapshot.distance_to_breakout_pct
            <= -SCORING_PRICE_EXTENSION_MIN_PERCENT
        )
        weak_rs = bool(
            components["relative_strength"].available
            and (
                (snapshot.rs_rating or 0) <= SCORING_WEAK_RS_RATING_MAX
                or snapshot.rs_deteriorating is True
                or (
                    snapshot.rs_6m_pct is not None
                    and snapshot.rs_12m_pct is not None
                    and snapshot.rs_6m_pct < 0
                    and snapshot.rs_12m_pct < 0
                )
            )
        )
        risk_conditions = {
            "PRICE_EXTENDED": price_extended,
            "RSI_EXTENDED": snapshot.rsi >= SCORING_RSI_EXTENDED_MIN,
            "HIGH_VOLATILITY": expanding_volatility,
            "DISTRIBUTION_VOLUME": distribution,
            "RESISTANCE_TOO_FAR": snapshot.resistance_too_far is True,
            "WEAK_RELATIVE_STRENGTH": weak_rs,
            "WEAK_MARKET_CONTEXT": snapshot.market_regime == "WEAK",
            "RISK_OFF_MARKET": snapshot.market_regime == "RISK_OFF",
            "LOW_LIQUIDITY": not snapshot.is_liquid,
            "INSUFFICIENT_HISTORY": insufficient,
            "STALE_MARKET_DATA": stale,
            "PIVOT_NOT_FOUND": not components["pivot"].available,
        }
        scoring_risk_flags = [
            flag for flag, detected in risk_conditions.items() if detected
        ]
        penalties = {
            flag: RISK_PENALTIES[flag] for flag in scoring_risk_flags
        }
        risk_flags = list(
            dict.fromkeys(
                [
                    *scoring_risk_flags,
                    *quality_risk_flags,
                    *snapshot.base_risk_flags,
                    *snapshot.pivot_quality_flags,
                    *snapshot.vcp_risk_flags,
                    *snapshot.market_risk_flags,
                ]
            )
        )
        penalized_score = normalize_score(raw_score - sum(penalties.values()))

        available_count = sum(component.available for component in components.values())
        confluent_count = sum(
            component.available
            and component.component_score
            >= component.max_component_score * SCORING_COMPONENT_CONFLUENCE_RATIO
            for component in components.values()
        )
        high_quality_confluence = bool(
            available_count >= SCORING_HIGH_QUALITY_MIN_AVAILABLE_COMPONENTS
            and confluent_count >= SCORING_HIGH_QUALITY_MIN_CONFLUENT_COMPONENTS
            and components["pivot"].available
            and components["relative_strength"].available
        )
        strong_confluence = bool(
            available_count >= SCORING_STRONG_MIN_AVAILABLE_COMPONENTS
            and confluent_count >= SCORING_STRONG_MIN_CONFLUENT_COMPONENTS
        )

        caps: list[tuple[str, int]] = []
        cap_conditions = (
            (not components["pivot"].available, "MISSING_PIVOT"),
            (not components["relative_strength"].available, "MISSING_RELATIVE_STRENGTH"),
            (stale, "STALE_MARKET_DATA"),
            (insufficient, "INSUFFICIENT_HISTORY"),
            (not snapshot.is_liquid, "LOW_LIQUIDITY"),
            (expanding_volatility, "HIGH_VOLATILITY"),
            (price_extended, "PRICE_EXTENDED"),
            (snapshot.rsi >= SCORING_RSI_EXTENDED_MIN, "RSI_EXTENDED"),
            (distribution, "DISTRIBUTION_VOLUME"),
            (snapshot.resistance_too_far is True, "RESISTANCE_TOO_FAR"),
            (snapshot.market_regime == "WEAK", "WEAK_MARKET"),
            (snapshot.market_regime == "RISK_OFF", "RISK_OFF_MARKET"),
            (not high_quality_confluence, "HIGH_QUALITY_CONFLUENCE"),
            (not strong_confluence, "STRONG_CONFLUENCE"),
            (quality_state == "PARTIAL", "QUALITY_PARTIAL"),
            (quality_state == "STALE", "QUALITY_STALE"),
            (quality_state not in {"FRESH", "PARTIAL", "STALE"}, "QUALITY_INVALID"),
        )
        for detected, cap_name in cap_conditions:
            if detected:
                caps.append((cap_name, CLASSIFICATION_SCORE_CAPS[cap_name]))
        final_score = min([penalized_score, *(cap for _, cap in caps)])

        positive_signals = list(
            dict.fromkeys([
                *(
                    f"{name.upper()}:{reason}"
                    for name, component in components.items()
                    for reason in component.supporting_reason_codes
                ),
                *(f"WEEKLY:{reason}" for reason in snapshot.weekly_reason_codes),
                *(f"BASE:{reason}" for reason in snapshot.base_reason_codes),
                *(f"RS_V2:{reason}" for reason in snapshot.rs_reason_codes),
                *(f"VOLUME_V2:{reason}" for reason in snapshot.volume_reason_codes),
            ])
        )
        component_quality = [
            flag
            for component in components.values()
            for flag in component.data_quality
        ]
        data_quality = list(
            dict.fromkeys(
                [
                    *snapshot.data_quality,
                    *snapshot.vcp_data_quality,
                    *snapshot.market_data_quality,
                    *component_quality,
                ]
            )
        )
        return PreBreakoutScoreResult(
            raw_prebreakout_score=raw_score,
            prebreakout_score=normalize_score(final_score),
            classification=classify_score(final_score),
            component_scores={
                name: component.as_mapping() for name, component in components.items()
            },
            positive_signals=positive_signals,
            risk_flags=risk_flags,
            data_quality=data_quality,
            applied_penalties=penalties,
            applied_caps=[name for name, _ in caps],
        )


prebreakout_scorer = PreBreakoutScorer()
