from __future__ import annotations

from dataclasses import asdict, dataclass, field
from math import isfinite
from typing import Any, Mapping


@dataclass(slots=True)
class SetupLifecycleFeatures:
    setup_lifecycle: str = "NO_SETUP"
    setup_readiness_score: int = 0
    sector_context_status: str = "SECTOR_CONTEXT_UNAVAILABLE"
    setup_reason_codes: list[str] = field(default_factory=list)
    setup_risk_flags: list[str] = field(default_factory=list)

    def as_mapping(self) -> dict[str, Any]:
        return asdict(self)


class SetupLifecycleFeatureExtractor:
    VALID_QUALITY_STATES = frozenset({"FRESH", "PARTIAL"})
    BREAKOUT_CONFIRMATION_PCT = 0.30
    EXTENSION_PCT = 3.0
    BREAKOUT_READY_MIN_SCORE = 75

    @staticmethod
    def _value(source: Any, name: str) -> Any:
        return source.get(name) if isinstance(source, Mapping) else getattr(source, name, None)

    @staticmethod
    def _number(value: Any) -> float | None:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed if isfinite(parsed) else None

    @staticmethod
    def _scaled(value: float | int | None, maximum: int) -> int:
        if value is None:
            return 0
        return round(max(0.0, min(float(value), 100.0)) / 100 * maximum)

    @classmethod
    def extract(
        cls,
        *,
        last_price: float | None,
        quality: Any,
        trend: Any,
        volatility: Any,
        volume: Any,
        structure: Any,
        pivot: Any,
        vcp: Any,
        base: Any,
        relative_strength: Any,
        weekly: Any,
        supply_demand: Any,
        overhead_supply: Any,
        failed_breakout: Any,
    ) -> SetupLifecycleFeatures:
        result = SetupLifecycleFeatures()
        quality_state = str(cls._value(quality, "data_quality_state") or "INVALID")
        lookback = int(cls._number(cls._value(quality, "lookback_sessions")) or 0)
        price = cls._number(last_price)
        pivot_level = cls._number(cls._value(pivot, "breakout_level"))
        distance = cls._number(cls._value(pivot, "distance_to_breakout_pct"))
        base_duration = int(cls._number(cls._value(base, "base_duration_sessions")) or 0)
        base_exists = bool(
            base_duration >= 10
            or cls._value(structure, "flat_base") is True
            or cls._value(structure, "ascending_triangle") is True
            or cls._value(structure, "darvas_consolidation") is True
        )
        vcp_risks = set(cls._value(vcp, "vcp_risk_flags") or [])
        severe_structure = bool(
            cls._value(vcp, "vcp_invalid") is True
            and vcp_risks.intersection({
                "EXPANDING_VOLATILITY", "LOOSE_RANDOM_RANGES",
                "EXCESSIVE_CONTRACTION_DEPTH", "WIDENING_CONTRACTIONS",
            })
        )
        invalid = bool(
            quality_state not in cls.VALID_QUALITY_STATES
            or price is None
            or lookback < 40
            or severe_structure
        )

        score = 0
        score += cls._scaled(cls._value(base, "base_quality_score"), 20)
        contraction_evidence = (
            cls._value(vcp, "depths_decreasing") is True,
            cls._value(vcp, "volatility_contracting") is True
            or cls._value(volatility, "atr_contracting") is True,
            cls._value(vcp, "volume_contracting") is True
            or cls._value(volume, "volume_dry_up") is True,
        )
        score += min(sum(5 for item in contraction_evidence if item), 15)
        if pivot_level is not None:
            score += 5
            score += cls._scaled(cls._value(pivot, "pivot_quality_score"), 5)
            if cls._value(pivot, "near_pivot") is True:
                score += 5
        score += cls._scaled(cls._value(relative_strength, "rs_rating"), 8)
        if cls._value(relative_strength, "rs_improving") is True:
            score += 4
        if cls._value(relative_strength, "rs_line_leading_price") is True:
            score += 3
        if cls._value(weekly, "weekly_trend") not in {None, "BEARISH"}:
            score += 4
        if cls._value(weekly, "daily_weekly_alignment") is True:
            score += 4
        if cls._value(weekly, "weekly_contraction") is True:
            score += 2
        demand_score = cls._number(cls._value(supply_demand, "demand_pressure_score"))
        supply_score = cls._number(cls._value(supply_demand, "supply_pressure_score"))
        score += cls._scaled(demand_score, 6)
        if supply_score is not None and supply_score < 35:
            score += 4
        overhead_score = cls._number(cls._value(overhead_supply, "overhead_supply_score"))
        if cls._value(overhead_supply, "overhead_supply_clear") is True:
            score += 10
        elif overhead_score is not None and overhead_score <= 25:
            score += 6
        failures = int(cls._number(cls._value(failed_breakout, "failed_breakout_count")) or 0)
        recent_failure = cls._value(failed_breakout, "recent_failed_breakout") is True
        if failures == 0:
            score += 5
        elif not recent_failure:
            score += 3

        risk_flags: list[str] = []
        caps: list[int] = []
        if quality_state == "PARTIAL":
            caps.append(70)
            risk_flags.append("PARTIAL_DATA_QUALITY")
        if invalid:
            caps.append(0)
            risk_flags.append("INVALID_SETUP_INPUT")
        if pivot_level is None:
            caps.append(35)
            risk_flags.append("PIVOT_MISSING")
        if cls._value(pivot, "resistance_too_far") is True or (
            distance is not None and distance > 5.0
        ):
            caps.append(45)
            risk_flags.append("PRICE_TOO_FAR_FROM_PIVOT")
        extended = bool(
            cls._value(base, "already_extended") is True
            or (distance is not None and distance <= -cls.EXTENSION_PCT)
            or (pivot_level and price and price >= pivot_level * (1 + cls.EXTENSION_PCT / 100))
        )
        if extended:
            caps.append(20)
            risk_flags.append("PRICE_EXTENDED")
        if cls._value(weekly, "weekly_trend") == "BEARISH":
            caps.append(50)
            risk_flags.append("WEEKLY_STRUCTURE_BEARISH")
        rs_rating = cls._number(cls._value(relative_strength, "rs_rating"))
        if rs_rating is not None and rs_rating < 40:
            caps.append(50)
            risk_flags.append("WEAK_RELATIVE_STRENGTH")
        if supply_score is not None and supply_score >= 60:
            caps.append(45)
            risk_flags.append("DISTRIBUTION_DOMINATES")
        if overhead_score is not None and overhead_score >= 55:
            caps.append(55)
            risk_flags.append("OVERHEAD_SUPPLY_HEAVY")
        if failures >= 2 and recent_failure:
            caps.append(50)
            risk_flags.append("REPEATED_FAILED_BREAKOUT")
        if severe_structure:
            caps.append(0)
            risk_flags.append("BROKEN_OR_EXPANDING_STRUCTURE")
        if caps:
            score = min(score, min(caps))
        result.setup_readiness_score = max(0, min(100, int(round(score))))

        contracting = bool(
            int(cls._number(cls._value(vcp, "contraction_count")) or 0) >= 2
            and any(contraction_evidence)
        )
        tightening = bool(
            cls._value(vcp, "depths_decreasing") is True
            and (
                cls._value(structure, "tight_closes") is True
                or cls._value(structure, "multiple_tight_closes") is True
                or cls._value(structure, "support_compression") is True
            )
            and (
                cls._value(vcp, "higher_lows_present") is True
                or cls._value(structure, "higher_lows") is True
            )
        )
        near_pivot = bool(
            pivot_level is not None
            and (
                cls._value(pivot, "near_pivot") is True
                or (distance is not None and abs(distance) <= 3.0)
            )
        )
        confirmed_cross = bool(
            pivot_level and price and price >= pivot_level * (1 + cls.BREAKOUT_CONFIRMATION_PCT / 100)
        )
        current_failure = bool(
            recent_failure
            and (cls._number(cls._value(failed_breakout, "days_since_failed_breakout")) or 999) <= 5
            and pivot_level and price and price < pivot_level
        )
        strong_trend = bool(
            cls._value(trend, "minervini_price_trend_template") is True
            or (
                cls._value(trend, "ema_alignment") is True
                and cls._value(trend, "price_above_sma_50") is True
            )
        )
        rs_confirmed = bool(
            (rs_rating is not None and rs_rating >= 65)
            or cls._value(relative_strength, "rs_improving") is True
            or cls._value(relative_strength, "rs_line_leading_price") is True
        )
        volume_constructive = bool(
            cls._value(volume, "volume_dry_up_near_pivot") is True
            or cls._value(volume, "volume_contracting_in_consolidation") is True
            or cls._value(supply_demand, "resistance_absorption_detected") is True
        )
        ready = bool(
            result.setup_readiness_score >= cls.BREAKOUT_READY_MIN_SCORE
            and strong_trend and rs_confirmed and near_pivot and volume_constructive
            and cls._value(weekly, "weekly_trend") != "BEARISH"
            and (supply_score is None or supply_score < 60)
            and cls._value(overhead_supply, "overhead_supply_clear") is True
            and not extended and not recent_failure and not invalid
        )

        if invalid:
            lifecycle = "INVALID_SETUP"
        elif current_failure:
            lifecycle = "FAILED_BREAKOUT"
        elif extended:
            lifecycle = "EXTENDED_AFTER_BREAKOUT"
        elif confirmed_cross:
            lifecycle = "BREAKOUT_IN_PROGRESS"
        elif ready:
            lifecycle = "BREAKOUT_READY"
        elif near_pivot and base_exists:
            lifecycle = "NEAR_PIVOT"
        elif tightening and base_exists:
            lifecycle = "TIGHTENING"
        elif contracting and base_exists:
            lifecycle = "CONTRACTING"
        elif base_exists and pivot_level is not None:
            lifecycle = "BASE_BUILDING"
        else:
            lifecycle = "NO_SETUP"
        result.setup_lifecycle = lifecycle

        reasons = [lifecycle]
        reason_pairs = (
            (base_exists, "BASE_BUILDING"),
            (contracting, "VOLATILITY_VOLUME_CONTRACTING"),
            (tightening, "VCP_TIGHTENING"),
            (near_pivot, "NEAR_PIVOT"),
            (cls._value(volume, "volume_dry_up_near_pivot") is True, "VOLUME_DRY_UP_NEAR_PIVOT"),
            (cls._value(relative_strength, "rs_line_leading_price") is True, "RS_LINE_LEADING_PRICE"),
            (cls._value(supply_demand, "resistance_absorption_detected") is True, "RESISTANCE_ABSORPTION"),
            (cls._value(overhead_supply, "overhead_supply_clear") is True, "OVERHEAD_SUPPLY_CLEAR"),
            (cls._value(weekly, "daily_weekly_alignment") is True, "WEEKLY_TREND_ALIGNED"),
        )
        reasons.extend(code for detected, code in reason_pairs if detected)
        result.setup_reason_codes = list(dict.fromkeys(reasons))
        result.setup_risk_flags = list(dict.fromkeys([
            *risk_flags,
            *(cls._value(supply_demand, "supply_demand_risk_flags") or []),
            *(cls._value(overhead_supply, "overhead_supply_risk_flags") or []),
            *(cls._value(failed_breakout, "failed_breakout_risk_flags") or []),
        ]))
        return result


setup_lifecycle_feature_extractor = SetupLifecycleFeatureExtractor()
