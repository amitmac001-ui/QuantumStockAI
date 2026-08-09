from __future__ import annotations

from dataclasses import asdict, dataclass, field
from math import isfinite
from statistics import median
from typing import Any, Mapping

import pandas as pd


@dataclass(slots=True)
class OverheadSupplyFeatures:
    overhead_supply_score: int | None = None
    overhead_supply_clear: bool | None = None
    nearest_overhead_resistance: float | None = None
    distance_to_overhead_resistance_pct: float | None = None
    overhead_resistance_count: int | None = None
    overhead_high_volume_zone_count: int | None = None
    overhead_supply_reason_codes: list[str] = field(default_factory=list)
    overhead_supply_risk_flags: list[str] = field(default_factory=list)

    def as_mapping(self) -> dict[str, Any]:
        return asdict(self)


class OverheadSupplyFeatureExtractor:
    MIN_HISTORY = 60
    LOOKBACK = 252
    SWING_WINDOW = 2
    MAX_OVERHEAD_DISTANCE_PCT = 15.0
    ZONE_TOLERANCE_PCT = 1.25
    NEARBY_DISTANCE_PCT = 5.0
    HEAVY_SCORE = 55

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
    def _swings(cls, work: pd.DataFrame, reference: float) -> list[dict[str, Any]]:
        rolling_volume = work["volume"].shift(1).rolling(20, min_periods=10).mean()
        swings = []
        for index in range(cls.SWING_WINDOW, len(work) - cls.SWING_WINDOW):
            level = float(work["high"].iloc[index])
            left = work["high"].iloc[index - cls.SWING_WINDOW:index]
            right = work["high"].iloc[index + 1:index + cls.SWING_WINDOW + 1]
            if not (level > left.max() and level >= right.max()):
                continue
            distance = (level - reference) / reference * 100
            if distance < 0.25 or distance > cls.MAX_OVERHEAD_DISTANCE_PCT:
                continue
            baseline = rolling_volume.iloc[index]
            high_volume = bool(
                pd.notna(baseline)
                and baseline > 0
                and work["volume"].iloc[index] >= baseline * 1.50
            )
            swings.append({"level": level, "index": index, "high_volume": high_volume})
        return swings

    @classmethod
    def _zones(cls, swings: list[dict[str, Any]], work: pd.DataFrame) -> list[dict[str, Any]]:
        zones: list[list[dict[str, Any]]] = []
        for swing in sorted(swings, key=lambda item: item["level"]):
            target = next(
                (
                    zone for zone in zones
                    if abs(swing["level"] - median(item["level"] for item in zone))
                    / median(item["level"] for item in zone) * 100
                    <= cls.ZONE_TOLERANCE_PCT
                ),
                None,
            )
            if target is None:
                zones.append([swing])
            else:
                target.append(swing)
        normalized = []
        for zone in zones:
            level = float(median(item["level"] for item in zone))
            tolerance = level * cls.ZONE_TOLERANCE_PCT / 100
            congestion = int(((work["close"] - level).abs() <= tolerance).sum())
            normalized.append({
                "level": level,
                "tests": len(zone),
                "high_volume": any(item["high_volume"] for item in zone),
                "congestion": congestion,
            })
        return normalized

    @classmethod
    def extract(
        cls,
        frame: pd.DataFrame,
        *,
        pivot: Any = None,
        current_price: float | None = None,
    ) -> OverheadSupplyFeatures:
        result = OverheadSupplyFeatures()
        work = cls._prepared(frame)
        pivot_level = cls._number(cls._value(pivot, "breakout_level"))
        current = cls._number(current_price) or (
            float(work["close"].iloc[-1]) if not work.empty else None
        )
        if len(work) < cls.MIN_HISTORY or current is None or pivot_level is None:
            result.overhead_supply_risk_flags.append("OVERHEAD_SUPPLY_DATA_UNAVAILABLE")
            return result

        reference = max(current, pivot_level)
        zones = cls._zones(cls._swings(work, reference), work)
        result.overhead_resistance_count = len(zones)
        result.overhead_high_volume_zone_count = sum(zone["high_volume"] for zone in zones)
        if not zones:
            result.overhead_supply_score = 0
            result.overhead_supply_clear = True
            result.overhead_supply_reason_codes.append("OVERHEAD_SUPPLY_CLEAR")
            return result

        nearest = min(zones, key=lambda zone: (zone["level"], -zone["tests"]))
        result.nearest_overhead_resistance = round(nearest["level"], 4)
        result.distance_to_overhead_resistance_pct = round(
            (nearest["level"] - current) / current * 100, 4
        )
        nearby = result.distance_to_overhead_resistance_pct <= cls.NEARBY_DISTANCE_PCT
        repeated_zones = sum(zone["tests"] >= 2 for zone in zones)
        congested_zones = sum(zone["congestion"] >= 3 for zone in zones)
        score = 0
        if result.distance_to_overhead_resistance_pct <= 3.0:
            score += 35
        elif nearby:
            score += 20
        score += min(len(zones) * 10, 30)
        score += min(repeated_zones * 10, 20)
        score += min(result.overhead_high_volume_zone_count * 10, 20)
        score += min(congested_zones * 10, 20)
        result.overhead_supply_score = min(score, 100)
        result.overhead_supply_clear = bool(
            result.overhead_supply_score < cls.HEAVY_SCORE and not nearby
        )

        if result.overhead_supply_clear:
            result.overhead_supply_reason_codes.append("OVERHEAD_SUPPLY_CLEAR")
        if repeated_zones:
            result.overhead_supply_reason_codes.append("PRIOR_RESISTANCE_ZONES_MAPPED")
        risk_pairs = (
            (nearby, "NEARBY_OVERHEAD_RESISTANCE"),
            (len(zones) >= 3, "MULTIPLE_OVERHEAD_RESISTANCE_ZONES"),
            (result.overhead_high_volume_zone_count > 0, "HIGH_VOLUME_OVERHEAD_ZONE"),
            (result.overhead_supply_score >= cls.HEAVY_SCORE, "OVERHEAD_SUPPLY_HEAVY"),
        )
        result.overhead_supply_risk_flags = [
            code for detected, code in risk_pairs if detected
        ]
        return result


overhead_supply_feature_extractor = OverheadSupplyFeatureExtractor()
