from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

import pandas as pd


@dataclass(slots=True)
class BaseQualityFeatures:
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

    def as_mapping(self) -> dict[str, Any]:
        return asdict(self)


class BaseQualityFeatureExtractor:
    LOOKBACK = 65

    @staticmethod
    def _value(source: Any, name: str) -> Any:
        return source.get(name) if isinstance(source, Mapping) else getattr(source, name, None)

    @classmethod
    def extract(cls, frame: pd.DataFrame, *, pivot: Any, structure: Any, vcp: Any) -> BaseQualityFeatures:
        result = BaseQualityFeatures()
        if frame.empty or not {"high", "low", "close"}.issubset(frame.columns):
            result.base_risk_flags.append("BASE_DATA_UNAVAILABLE")
            return result
        clean = frame.loc[:, ["high", "low", "close"]].apply(pd.to_numeric, errors="coerce").dropna()
        if clean.empty:
            result.base_risk_flags.append("BASE_DATA_UNAVAILABLE")
            return result
        base = clean.tail(cls.LOOKBACK)
        pivot_level = cls._value(pivot, "breakout_level")
        if pivot_level is not None and float(pivot_level) > 0:
            pivot_level = float(pivot_level)
            within_base = base.loc[base["close"] <= pivot_level * 1.03]
            result.base_duration_sessions = len(within_base)
            base_low = float(base["low"].min())
            result.base_depth_pct = round((pivot_level - base_low) / pivot_level * 100, 4)
            high_52 = float(clean.tail(252)["high"].max())
            result.overhead_resistance_pct = round(max(high_52 - pivot_level, 0) / pivot_level * 100, 4)
            result.overhead_resistance_clear = result.overhead_resistance_pct <= 5.0

        depths = [float(value) for value in (cls._value(vcp, "contraction_depths") or [])]
        result.progressively_smaller_contractions = bool(
            len(depths) >= 2 and all(current < previous for previous, current in zip(depths, depths[1:]))
        )
        result.premature_breakout = cls._value(pivot, "already_above_pivot") is True
        distance = cls._value(pivot, "distance_to_breakout_pct")
        result.already_extended = bool(distance is not None and float(distance) <= -3.0)

        confirmations = (
            result.base_duration_sessions is not None and result.base_duration_sessions >= 15,
            result.base_depth_pct is not None and 3.0 <= result.base_depth_pct <= 35.0,
            cls._value(vcp, "contraction_count") is not None and int(cls._value(vcp, "contraction_count")) >= 2,
            result.progressively_smaller_contractions,
            cls._value(structure, "tight_closes") is True or cls._value(structure, "multiple_tight_closes") is True,
            cls._value(pivot, "pivot_test_count") is not None and int(cls._value(pivot, "pivot_test_count")) >= 2,
            cls._value(pivot, "near_pivot") is True,
            result.overhead_resistance_clear,
        )
        result.base_quality_score = round(sum(bool(value) for value in confirmations) / len(confirmations) * 100)
        reason_pairs = (
            (confirmations[0], "ADEQUATE_BASE_DURATION"),
            (confirmations[1], "CONTROLLED_BASE_DEPTH"),
            (confirmations[2], "MULTIPLE_CONTRACTIONS"),
            (confirmations[3], "PROGRESSIVELY_SMALLER_CONTRACTIONS"),
            (confirmations[4], "TIGHT_CLOSES_IN_BASE"),
            (confirmations[5], "REPEATED_PIVOT_TESTS"),
            (confirmations[6], "NEAR_PIVOT"),
            (confirmations[7], "CLEAR_OVERHEAD_RESISTANCE"),
        )
        result.base_reason_codes = [code for detected, code in reason_pairs if detected]
        risk_pairs = (
            (result.base_duration_sessions is not None and result.base_duration_sessions < 10, "BASE_TOO_SHORT"),
            (result.base_depth_pct is not None and result.base_depth_pct > 35.0, "BASE_TOO_DEEP"),
            (result.overhead_resistance_clear is False, "OVERHEAD_RESISTANCE"),
            (result.premature_breakout, "PREMATURE_BREAKOUT"),
            (result.already_extended, "ALREADY_EXTENDED"),
        )
        result.base_risk_flags = [code for detected, code in risk_pairs if detected]
        return result


base_quality_feature_extractor = BaseQualityFeatureExtractor()
