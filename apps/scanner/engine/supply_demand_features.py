from __future__ import annotations

from dataclasses import asdict, dataclass, field
from math import isfinite
from typing import Any, Mapping

import pandas as pd


@dataclass(slots=True)
class SupplyDemandFeatures:
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

    def as_mapping(self) -> dict[str, Any]:
        return asdict(self)


class SupplyDemandFeatureExtractor:
    MIN_HISTORY = 30
    LOOKBACK = 50
    PRESSURE_LOOKBACK = 20
    PULLBACK_RECENT = 10
    PULLBACK_BASELINE = 20
    PIVOT_TEST_LOOKBACK = 35
    PIVOT_TOLERANCE_PCT = 1.5

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

    @classmethod
    def _prepared(cls, frame: pd.DataFrame) -> pd.DataFrame:
        required = {"high", "low", "close", "volume"}
        if frame.empty or not required.issubset(frame.columns):
            return pd.DataFrame()
        clean = frame.loc[:, ["high", "low", "close", "volume"]].apply(
            pd.to_numeric, errors="coerce"
        ).dropna()
        clean = clean.loc[
            (clean[["high", "low", "close"]] > 0).all(axis=1)
            & (clean["volume"] >= 0)
            & (clean["high"] >= clean[["low", "close"]].max(axis=1))
            & (clean["low"] <= clean[["high", "close"]].min(axis=1))
        ]
        return clean.tail(cls.LOOKBACK).reset_index(drop=True)

    @classmethod
    def _resistance_absorption(
        cls, work: pd.DataFrame, pivot_level: float | None
    ) -> bool | None:
        if pivot_level is None or pivot_level <= 0:
            return None
        window = work.tail(cls.PIVOT_TEST_LOOKBACK)
        tolerance = pivot_level * cls.PIVOT_TOLERANCE_PCT / 100
        tests = window.loc[(window["high"] - pivot_level).abs() <= tolerance].copy()
        if len(tests) < 3:
            return False
        rejection = ((tests["high"] - tests["close"]) / pivot_level * 100).clip(lower=0)
        midpoint = max(1, len(tests) // 2)
        early_rejection = float(rejection.iloc[:midpoint].mean())
        late_rejection = float(rejection.iloc[midpoint:].mean())
        early_volume = float(tests["volume"].iloc[:midpoint].mean())
        late_volume = float(tests["volume"].iloc[midpoint:].mean())
        close_progress = float(tests["close"].iloc[-1]) >= float(tests["close"].iloc[0])
        return bool(
            late_rejection <= early_rejection * 0.80
            and late_volume <= early_volume * 1.10
            and close_progress
        )

    @classmethod
    def extract(
        cls,
        frame: pd.DataFrame,
        *,
        pivot: Any = None,
        volume: Any = None,
    ) -> SupplyDemandFeatures:
        result = SupplyDemandFeatures()
        work = cls._prepared(frame)
        if len(work) < cls.MIN_HISTORY:
            result.supply_demand_risk_flags.append("SUPPLY_DEMAND_DATA_UNAVAILABLE")
            return result

        changes = work["close"].pct_change()
        pressure = work.tail(cls.PRESSURE_LOOKBACK).copy()
        pressure_changes = changes.tail(cls.PRESSURE_LOOKBACK)
        up_volume = float(pressure.loc[pressure_changes > 0, "volume"].sum())
        down_volume = float(pressure.loc[pressure_changes < 0, "volume"].sum())
        total_directional_volume = up_volume + down_volume
        if total_directional_volume > 0:
            result.accumulation_distribution_balance = round(
                (up_volume - down_volume) / total_directional_volume * 100, 4
            )

        recent = work.tail(cls.PULLBACK_RECENT)
        baseline = work.iloc[-(cls.PULLBACK_RECENT + cls.PULLBACK_BASELINE):-cls.PULLBACK_RECENT]
        recent_changes = changes.tail(cls.PULLBACK_RECENT)
        baseline_changes = changes.iloc[
            -(cls.PULLBACK_RECENT + cls.PULLBACK_BASELINE):-cls.PULLBACK_RECENT
        ]
        recent_down_volume = recent.loc[recent_changes < 0, "volume"]
        baseline_down_volume = baseline.loc[baseline_changes < 0, "volume"]
        if len(recent_down_volume) >= 2 and len(baseline_down_volume) >= 2:
            result.pullback_volume_contracting = bool(
                recent_down_volume.mean() <= baseline_down_volume.mean() * 0.85
            )
            recent_declines = recent_changes.loc[recent_changes < 0].abs()
            baseline_declines = baseline_changes.loc[baseline_changes < 0].abs()
            result.selling_pressure_declining = bool(
                result.pullback_volume_contracting
                and not recent_declines.empty
                and not baseline_declines.empty
                and recent_declines.mean() <= baseline_declines.mean() * 1.10
            )

        prior_volume = work["volume"].shift(1).rolling(20, min_periods=10).mean()
        candle_range = (work["high"] - work["low"]).replace(0, pd.NA)
        close_location = (work["close"] - work["low"]) / candle_range
        constructive = (
            (changes > 0)
            & (work["volume"] >= prior_volume * 1.25)
            & (close_location >= 0.65)
        )
        result.demand_expansion_detected = bool(constructive.tail(10).sum() >= 1)

        pivot_level = cls._number(cls._value(pivot, "breakout_level"))
        result.resistance_absorption_detected = cls._resistance_absorption(
            work, pivot_level
        )

        price_return = float(work["close"].iloc[-1] / work["close"].iloc[-21] - 1) * 100
        recent_avg_volume = float(work["volume"].tail(20).mean())
        baseline_avg_volume = float(work["volume"].iloc[-40:-20].mean())
        if baseline_avg_volume > 0:
            volume_ratio = recent_avg_volume / baseline_avg_volume
            result.price_progress_per_volume = round(price_return / max(volume_ratio, 0.25), 4)

        balance = result.accumulation_distribution_balance
        accumulation_behavior = cls._value(volume, "accumulation_behavior") is True
        distribution_days = cls._number(cls._value(volume, "distribution_days")) or 0
        accumulation_days = cls._number(cls._value(volume, "accumulation_days")) or 0
        demand_checks = (
            balance is not None and balance >= 15,
            result.pullback_volume_contracting is True,
            result.selling_pressure_declining is True,
            result.resistance_absorption_detected is True,
            result.demand_expansion_detected is True or accumulation_behavior,
        )
        result.demand_pressure_score = sum(20 for confirmed in demand_checks if confirmed)

        recent_supply_expanding = bool(
            result.pullback_volume_contracting is False
            and len(recent_down_volume) >= 2
            and len(baseline_down_volume) >= 2
            and recent_down_volume.mean() >= baseline_down_volume.mean() * 1.20
        )
        supply_points = (
            (balance is not None and balance <= -15, 30),
            (distribution_days > accumulation_days and distribution_days >= 3, 25),
            (recent_supply_expanding, 25),
            (result.selling_pressure_declining is False, 10),
            (cls._value(volume, "abnormal_volume") is True, 10),
        )
        result.supply_pressure_score = min(
            100, sum(points for detected, points in supply_points if detected)
        )

        reason_pairs = (
            (balance is not None and balance >= 15, "UP_VOLUME_PRESSURE_DOMINANT"),
            (result.pullback_volume_contracting, "PULLBACK_VOLUME_CONTRACTING"),
            (result.selling_pressure_declining, "SELLING_PRESSURE_DECLINING"),
            (result.resistance_absorption_detected, "RESISTANCE_ABSORPTION"),
            (result.demand_expansion_detected, "DEMAND_EXPANSION"),
        )
        result.supply_demand_reason_codes = [
            code for detected, code in reason_pairs if detected is True
        ]
        risk_pairs = (
            (balance is not None and balance <= -15, "DISTRIBUTION_PRESSURE_DOMINANT"),
            (recent_supply_expanding, "SELLING_VOLUME_EXPANDING"),
            (result.supply_pressure_score >= 60, "HEAVY_SUPPLY_PRESSURE"),
            (cls._value(volume, "abnormal_volume") is True, "ABNORMAL_VOLUME_INPUT"),
        )
        result.supply_demand_risk_flags = [
            code for detected, code in risk_pairs if detected
        ]
        return result


supply_demand_feature_extractor = SupplyDemandFeatureExtractor()
