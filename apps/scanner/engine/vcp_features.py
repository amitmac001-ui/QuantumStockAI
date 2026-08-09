from __future__ import annotations

from dataclasses import asdict, dataclass, field
from math import isfinite
from typing import Any, Mapping

import pandas as pd

from .prebreakout_config import (
    VCP_DETECTED_MIN_QUALITY_SCORE,
    VCP_DEPTH_DECREASE_MAX_RATIO,
    VCP_EXPANDING_VOLATILITY_MIN_RATIO,
    VCP_EXTREMA_WINDOW,
    VCP_HEAVY_DISTRIBUTION_MIN_DAYS,
    VCP_HIGHER_LOW_MIN_RISE_PERCENT,
    VCP_MAX_CONTRACTION_DEPTH_PERCENT,
    VCP_MAX_CONTRACTION_DURATION,
    VCP_MAX_REPORTED_CONTRACTIONS,
    VCP_MIN_CONTRACTION_DEPTH_PERCENT,
    VCP_MIN_CONTRACTION_DURATION,
    VCP_MIN_CONTRACTIONS,
    VCP_MIN_HISTORY,
    VCP_MIN_INDEPENDENT_CONFIRMATIONS,
    VCP_QUALITY_POINTS,
    VCP_WIDENING_MIN_RATIO,
)


@dataclass(slots=True)
class VCPFeatures:
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

    def as_mapping(self) -> dict[str, Any]:
        return asdict(self)


class VCPFeatureExtractor:
    """Deterministic VCP confirmations composed from prior-phase features."""

    REQUIRED_COLUMNS = frozenset({"high", "low", "close"})

    @staticmethod
    def _value(features: Any, name: str) -> Any:
        if isinstance(features, Mapping):
            return features.get(name)
        return getattr(features, name, None)

    @staticmethod
    def _number(value: Any) -> float | None:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed if isfinite(parsed) else None

    @classmethod
    def _local_extrema(cls, close: pd.Series) -> tuple[list[int], list[int]]:
        peaks: list[int] = []
        troughs: list[int] = []
        for index in range(VCP_EXTREMA_WINDOW, len(close) - VCP_EXTREMA_WINDOW):
            value = float(close.iloc[index])
            left = close.iloc[index - VCP_EXTREMA_WINDOW:index]
            right = close.iloc[index + 1:index + VCP_EXTREMA_WINDOW + 1]
            if value > left.max() and value >= right.max():
                peaks.append(index)
            if value < left.min() and value <= right.min():
                troughs.append(index)
        return peaks, troughs

    @classmethod
    def _contractions(cls, frame: pd.DataFrame) -> list[dict[str, Any]]:
        peaks, troughs = cls._local_extrema(frame["close"])
        contractions: list[dict[str, Any]] = []
        for position, peak_index in enumerate(peaks):
            next_peak = peaks[position + 1] if position + 1 < len(peaks) else len(frame)
            eligible_troughs = [
                index for index in troughs if peak_index < index < next_peak
            ]
            if not eligible_troughs:
                continue
            trough_index = min(
                eligible_troughs,
                key=lambda index: (float(frame["low"].iloc[index]), index),
            )
            peak = float(frame["high"].iloc[peak_index])
            trough = float(frame["low"].iloc[trough_index])
            duration = trough_index - peak_index
            if peak <= 0 or trough <= 0 or duration <= 0:
                continue
            depth = (peak - trough) / peak * 100
            if (
                depth < VCP_MIN_CONTRACTION_DEPTH_PERCENT
                or duration < VCP_MIN_CONTRACTION_DURATION
                or duration > VCP_MAX_CONTRACTION_DURATION
            ):
                continue
            contractions.append(
                {
                    "peak_index": peak_index,
                    "trough_index": trough_index,
                    "depth_pct": round(depth, 4),
                    "duration": duration,
                    "trough": trough,
                }
            )
        return contractions[-VCP_MAX_REPORTED_CONTRACTIONS:]

    @classmethod
    def _volatility_contracting(cls, volatility: Any) -> tuple[bool | None, bool]:
        confirmations = [
            cls._value(volatility, "atr_contracting"),
            cls._value(volatility, "rolling_range_compressed"),
            cls._value(volatility, "candle_range_contracting"),
            cls._value(volatility, "stddev_contracting"),
            cls._value(volatility, "bollinger_squeeze"),
        ]
        available = [value for value in confirmations if value is not None]
        contracting = any(value is True for value in available) if available else None
        ratios = [
            cls._number(cls._value(volatility, name))
            for name in (
                "atr_contraction_ratio",
                "rolling_range_contraction_ratio",
                "candle_range_contraction_ratio",
                "stddev_contraction_ratio",
            )
        ]
        expanding = any(
            ratio is not None and ratio >= VCP_EXPANDING_VOLATILITY_MIN_RATIO
            for ratio in ratios
        )
        return contracting, expanding

    @classmethod
    def _volume_contracting(cls, volume: Any) -> tuple[bool | None, bool]:
        available = [
            cls._value(volume, "volume_dry_up"),
            cls._value(volume, "volume_contracting_in_consolidation"),
        ]
        available = [value for value in available if value is not None]
        contracting = any(value is True for value in available) if available else None

        accumulation = cls._number(cls._value(volume, "accumulation_days"))
        distribution = cls._number(cls._value(volume, "distribution_days"))
        up_volume = cls._number(cls._value(volume, "up_volume"))
        down_volume = cls._number(cls._value(volume, "down_volume"))
        heavy_distribution = bool(
            distribution is not None
            and distribution >= VCP_HEAVY_DISTRIBUTION_MIN_DAYS
            and (accumulation is None or distribution > accumulation)
            and down_volume is not None
            and up_volume is not None
            and down_volume > up_volume
        )
        return contracting, heavy_distribution

    @classmethod
    def extract(
        cls,
        frame: pd.DataFrame,
        *,
        volatility: Any = None,
        volume: Any = None,
        price_structure: Any = None,
        pivot: Any = None,
    ) -> VCPFeatures:
        result = VCPFeatures()
        if frame.empty:
            result.vcp_data_quality.extend(
                ["MISSING_CANDLE_DATA", "INSUFFICIENT_VCP_HISTORY"]
            )
            return result
        if not cls.REQUIRED_COLUMNS.issubset(frame.columns):
            result.vcp_data_quality.append("VCP_PRICE_DATA_UNAVAILABLE")
            return result

        clean = frame.loc[:, ["high", "low", "close"]].apply(
            pd.to_numeric, errors="coerce"
        ).dropna()
        clean = clean.loc[
            (clean > 0).all(axis=1)
            & (clean["high"] >= clean[["low", "close"]].max(axis=1))
            & (clean["low"] <= clean[["high", "close"]].min(axis=1))
        ].reset_index(drop=True)
        if len(clean) < VCP_MIN_HISTORY:
            result.vcp_data_quality.append("INSUFFICIENT_VCP_HISTORY")
            return result

        contractions = cls._contractions(clean)
        result.contraction_depths = [item["depth_pct"] for item in contractions]
        result.contraction_durations = [item["duration"] for item in contractions]
        result.contraction_count = len(contractions)
        if result.contraction_count >= VCP_MIN_CONTRACTIONS:
            result.depths_decreasing = all(
                current <= previous * VCP_DEPTH_DECREASE_MAX_RATIO
                for previous, current in zip(
                    result.contraction_depths, result.contraction_depths[1:]
                )
            )
            result.t1_t2_t3_tightening = (
                result.contraction_count >= 3 and result.depths_decreasing
            )

        result.volatility_contracting, expanding_volatility = (
            cls._volatility_contracting(volatility)
        )
        result.volume_contracting, heavy_distribution = cls._volume_contracting(
            volume
        )
        structure_higher_lows = cls._value(price_structure, "higher_lows") is True
        tightening_support = (
            cls._value(price_structure, "support_compression") is True
        )
        contraction_higher_lows = bool(
            len(contractions) >= 2
            and all(
                current["trough"]
                >= previous["trough"]
                * (1 + VCP_HIGHER_LOW_MIN_RISE_PERCENT / 100)
                for previous, current in zip(contractions, contractions[1:])
            )
        )
        result.higher_lows_present = bool(
            structure_higher_lows or tightening_support or contraction_higher_lows
        )

        pivot_available = cls._number(cls._value(pivot, "breakout_level")) is not None
        pivot_near = cls._value(pivot, "near_pivot") is True
        pivot_too_far = cls._value(pivot, "resistance_too_far") is True
        tight_structure = any(
            cls._value(price_structure, name) is True
            for name in (
                "tight_closes",
                "multiple_tight_closes",
                "support_compression",
            )
        )
        result.tight_near_pivot = bool(
            pivot_available and pivot_near and not pivot_too_far and tight_structure
        )

        widening = bool(
            len(result.contraction_depths) >= 2
            and any(
                current >= previous * VCP_WIDENING_MIN_RATIO
                for previous, current in zip(
                    result.contraction_depths, result.contraction_depths[1:]
                )
            )
        )
        excessive_depth = any(
            depth > VCP_MAX_CONTRACTION_DEPTH_PERCENT
            for depth in result.contraction_depths
        )
        loose_structure = bool(
            result.contraction_count >= VCP_MIN_CONTRACTIONS
            and result.depths_decreasing is False
            and not tight_structure
            and not result.higher_lows_present
        )

        risk_pairs = (
            (result.contraction_count < VCP_MIN_CONTRACTIONS, "TOO_FEW_CONTRACTIONS"),
            (widening, "WIDENING_CONTRACTIONS"),
            (expanding_volatility, "EXPANDING_VOLATILITY"),
            (heavy_distribution, "HEAVY_DISTRIBUTION"),
            (loose_structure, "LOOSE_RANDOM_RANGES"),
            (not pivot_available, "NO_MEANINGFUL_PIVOT"),
            (excessive_depth, "EXCESSIVE_CONTRACTION_DEPTH"),
            (pivot_too_far, "PRICE_TOO_FAR_FROM_PIVOT"),
        )
        result.vcp_risk_flags = [flag for detected, flag in risk_pairs if detected]

        confirmation_pairs = (
            (result.contraction_count >= VCP_MIN_CONTRACTIONS, "MULTIPLE_CONTRACTIONS"),
            (result.depths_decreasing, "PROGRESSIVELY_SMALLER_CONTRACTIONS"),
            (result.volatility_contracting, "VOLATILITY_CONTRACTING"),
            (result.volume_contracting, "VOLUME_CONTRACTING"),
            (result.higher_lows_present, "HIGHER_LOWS_SUPPORT"),
            (result.tight_near_pivot, "TIGHT_NEAR_PIVOT"),
        )
        result.vcp_reason_codes = [
            reason for confirmed, reason in confirmation_pairs if confirmed is True
        ]
        if result.t1_t2_t3_tightening:
            result.vcp_reason_codes.append("T1_T2_T3_TIGHTENING")
        result.independent_confirmation_count = sum(
            confirmed is True for confirmed, _ in confirmation_pairs
        )

        score_keys = (
            (result.contraction_count >= VCP_MIN_CONTRACTIONS, "multiple_contractions"),
            (result.depths_decreasing, "decreasing_depths"),
            (result.volatility_contracting, "volatility_contracting"),
            (result.volume_contracting, "volume_contracting"),
            (result.higher_lows_present, "higher_lows"),
            (result.tight_near_pivot, "tight_near_pivot"),
        )
        result.vcp_quality_score = sum(
            VCP_QUALITY_POINTS[key] for confirmed, key in score_keys if confirmed is True
        )
        fatal_flags = {
            "WIDENING_CONTRACTIONS",
            "EXPANDING_VOLATILITY",
            "HEAVY_DISTRIBUTION",
            "LOOSE_RANDOM_RANGES",
            "NO_MEANINGFUL_PIVOT",
            "EXCESSIVE_CONTRACTION_DEPTH",
            "PRICE_TOO_FAR_FROM_PIVOT",
        }
        result.vcp_invalid = any(flag in fatal_flags for flag in result.vcp_risk_flags)
        result.vcp_detected = bool(
            not result.vcp_invalid
            and result.contraction_count >= VCP_MIN_CONTRACTIONS
            and result.independent_confirmation_count
            >= VCP_MIN_INDEPENDENT_CONFIRMATIONS
            and result.vcp_quality_score >= VCP_DETECTED_MIN_QUALITY_SCORE
        )
        return result


vcp_feature_extractor = VCPFeatureExtractor()
