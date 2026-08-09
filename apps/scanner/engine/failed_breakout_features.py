from __future__ import annotations

from dataclasses import asdict, dataclass, field
from math import isfinite
from typing import Any, Mapping

import pandas as pd


@dataclass(slots=True)
class FailedBreakoutFeatures:
    failed_breakout_count: int | None = None
    recent_failed_breakout: bool | None = None
    days_since_failed_breakout: int | None = None
    same_zone_failure_count: int | None = None
    failure_severity: str | None = None
    failed_breakout_reason_codes: list[str] = field(default_factory=list)
    failed_breakout_risk_flags: list[str] = field(default_factory=list)

    def as_mapping(self) -> dict[str, Any]:
        return asdict(self)


class FailedBreakoutFeatureExtractor:
    MIN_HISTORY = 40
    LOOKBACK = 160
    CLOSE_CONFIRMATION_PCT = 0.30
    FAILURE_CLOSE_PCT = 1.00
    CONFIRMATION_SESSIONS = 5
    RECENT_SESSIONS = 40

    @staticmethod
    def _value(source: Any, name: str) -> Any:
        return source.get(name) if isinstance(source, Mapping) else getattr(source, name, None)

    @staticmethod
    def _number(value: Any) -> float | None:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed if isfinite(parsed) and parsed > 0 else None

    @classmethod
    def _prepared(cls, frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty or not {"high", "close"}.issubset(frame.columns):
            return pd.DataFrame()
        clean = frame.loc[:, ["high", "close"]].apply(
            pd.to_numeric, errors="coerce"
        ).dropna()
        clean = clean.loc[(clean > 0).all(axis=1) & (clean["high"] >= clean["close"])]
        return clean.tail(cls.LOOKBACK).reset_index(drop=True)

    @classmethod
    def extract(cls, frame: pd.DataFrame, *, pivot: Any = None) -> FailedBreakoutFeatures:
        result = FailedBreakoutFeatures()
        work = cls._prepared(frame)
        pivot_level = cls._number(cls._value(pivot, "breakout_level"))
        if len(work) < cls.MIN_HISTORY or pivot_level is None:
            result.failed_breakout_risk_flags.append("FAILED_BREAKOUT_DATA_UNAVAILABLE")
            return result

        breakout_close = pivot_level * (1 + cls.CLOSE_CONFIRMATION_PCT / 100)
        pre_breakout_ceiling = pivot_level * (1 + cls.CLOSE_CONFIRMATION_PCT / 200)
        failure_close = pivot_level * (1 - cls.FAILURE_CLOSE_PCT / 100)
        failures: list[dict[str, float | int]] = []
        last_eligible = len(work) - cls.CONFIRMATION_SESSIONS
        for index in range(1, last_eligible):
            if not (
                float(work["close"].iloc[index - 1]) <= pre_breakout_ceiling
                and float(work["close"].iloc[index]) >= breakout_close
            ):
                continue
            confirmation = work.iloc[index + 1:index + 1 + cls.CONFIRMATION_SESSIONS]
            failed_rows = confirmation.loc[confirmation["close"] <= failure_close]
            if failed_rows.empty:
                continue
            failure_index = int(failed_rows.index[0])
            lowest_close = float(confirmation["close"].min())
            severity_pct = max(0.0, (pivot_level - lowest_close) / pivot_level * 100)
            failures.append({
                "attempt_index": index,
                "failure_index": failure_index,
                "severity_pct": severity_pct,
            })

        result.failed_breakout_count = len(failures)
        result.same_zone_failure_count = len(failures)
        result.recent_failed_breakout = False
        result.failure_severity = "NONE"
        if failures:
            latest = failures[-1]
            result.days_since_failed_breakout = len(work) - 1 - int(latest["failure_index"])
            result.recent_failed_breakout = (
                result.days_since_failed_breakout <= cls.RECENT_SESSIONS
            )
            maximum_severity = max(float(item["severity_pct"]) for item in failures)
            if maximum_severity >= 5.0:
                result.failure_severity = "SEVERE"
            elif maximum_severity >= 3.0:
                result.failure_severity = "MODERATE"
            else:
                result.failure_severity = "LOW"
            result.failed_breakout_reason_codes.append("PRIOR_CONFIRMED_BREAKOUT_FAILURE")
            if result.recent_failed_breakout:
                result.failed_breakout_risk_flags.append("RECENT_FAILED_BREAKOUT")
            if len(failures) >= 2:
                result.failed_breakout_risk_flags.append("REPEATED_FAILED_BREAKOUT")
            if result.failure_severity == "SEVERE":
                result.failed_breakout_risk_flags.append("SEVERE_BREAKOUT_FAILURE")
        else:
            result.failed_breakout_reason_codes.append("NO_CONFIRMED_FAILED_BREAKOUT")
        return result


failed_breakout_feature_extractor = FailedBreakoutFeatureExtractor()
