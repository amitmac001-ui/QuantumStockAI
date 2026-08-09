from __future__ import annotations

from dataclasses import asdict, dataclass, field
from math import isfinite
from statistics import median
from typing import Any, Mapping

import pandas as pd

from .prebreakout_config import (
    PIVOT_CONSOLIDATION_LOOKBACK,
    PIVOT_LOOKBACK,
    PIVOT_LOW_QUALITY_SCORE,
    PIVOT_MAX_BREACH_PERCENT,
    PIVOT_MAX_CONSOLIDATION_DEPTH_PERCENT,
    PIVOT_MIN_CEILING_TESTS,
    PIVOT_MIN_HISTORY,
    PIVOT_MIN_RESISTANCE_TESTS,
    PIVOT_MIN_SWING_PROMINENCE_PERCENT,
    PIVOT_MIN_TEST_SEPARATION,
    PIVOT_NEAR_MAX_DISTANCE_PERCENT,
    PIVOT_RESISTANCE_TOLERANCE_PERCENT,
    PIVOT_SOURCE_BASE_QUALITY,
    PIVOT_SWING_WINDOW,
    PIVOT_TOO_FAR_DISTANCE_PERCENT,
)


@dataclass(slots=True)
class PivotFeatures:
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
    data_quality: list[str] = field(default_factory=list)

    def as_mapping(self) -> dict[str, Any]:
        return asdict(self)


class PivotFeatureExtractor:
    """Objective pivot selection without changing legacy breakout behaviour."""

    REQUIRED_COLUMNS = frozenset({"high", "low", "close"})

    @staticmethod
    def _number(value: Any) -> float | None:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed if isfinite(parsed) and parsed > 0 else None

    @staticmethod
    def _structure_value(structure: Any, name: str) -> Any:
        if isinstance(structure, Mapping):
            return structure.get(name)
        return getattr(structure, name, None)

    @staticmethod
    def _distance(level: float, current_price: float) -> float:
        return round((level - current_price) / current_price * 100, 4)

    @classmethod
    def _swing_highs(cls, frame: pd.DataFrame) -> list[dict[str, Any]]:
        swings: list[dict[str, Any]] = []
        for index in range(PIVOT_SWING_WINDOW, len(frame) - PIVOT_SWING_WINDOW):
            level = float(frame["high"].iloc[index])
            left_highs = frame["high"].iloc[index - PIVOT_SWING_WINDOW:index]
            right_highs = frame["high"].iloc[index + 1:index + PIVOT_SWING_WINDOW + 1]
            if not (level > left_highs.max() and level >= right_highs.max()):
                continue
            left_low = float(
                frame["low"].iloc[index - PIVOT_SWING_WINDOW:index + 1].min()
            )
            right_low = float(
                frame["low"].iloc[index:index + PIVOT_SWING_WINDOW + 1].min()
            )
            prominence = (level - max(left_low, right_low)) / level * 100
            if prominence < PIVOT_MIN_SWING_PROMINENCE_PERCENT:
                continue
            swings.append(
                {
                    "level": level,
                    "index": index,
                    "age": len(frame) - 1 - index,
                    "prominence_pct": round(prominence, 4),
                }
            )
        return swings

    @staticmethod
    def _separated_test_count(indices: list[int]) -> int:
        count = 0
        last: int | None = None
        for index in sorted(indices):
            if last is None or index - last >= PIVOT_MIN_TEST_SEPARATION:
                count += 1
                last = index
        return count

    @classmethod
    def _cluster_swings(cls, swings: list[dict[str, Any]]) -> list[dict[str, Any]]:
        clusters: list[list[dict[str, Any]]] = []
        for swing in sorted(swings, key=lambda item: (item["level"], item["index"])):
            target = None
            for cluster in clusters:
                center = median(item["level"] for item in cluster)
                if abs(swing["level"] - center) / center * 100 <= PIVOT_RESISTANCE_TOLERANCE_PERCENT:
                    target = cluster
                    break
            if target is None:
                clusters.append([swing])
            else:
                target.append(swing)

        candidates = []
        for cluster in clusters:
            test_count = cls._separated_test_count(
                [int(item["index"]) for item in cluster]
            )
            if test_count < PIVOT_MIN_RESISTANCE_TESTS:
                continue
            candidates.append(
                {
                    "level": float(median(item["level"] for item in cluster)),
                    "sources": {"REPEATED_RESISTANCE"},
                    "test_count": test_count,
                    "age": min(int(item["age"]) for item in cluster),
                }
            )
        return candidates

    @classmethod
    def _ceiling_candidate(
        cls, frame: pd.DataFrame, price_structure: Any
    ) -> dict[str, Any] | None:
        window = frame.tail(PIVOT_CONSOLIDATION_LOOKBACK).reset_index(drop=True)
        if len(window) < PIVOT_CONSOLIDATION_LOOKBACK:
            return None
        reference = float(window["high"].quantile(0.90))
        tolerance = reference * PIVOT_RESISTANCE_TOLERANCE_PERCENT / 100
        touches = window.loc[
            (window["high"] >= reference - tolerance)
            & (window["high"] <= reference + tolerance)
        ]
        test_count = cls._separated_test_count(list(touches.index))
        if test_count < PIVOT_MIN_CEILING_TESTS:
            return None
        level = float(touches["high"].median())
        depth = (level - float(window["low"].min())) / level * 100
        if depth > PIVOT_MAX_CONSOLIDATION_DEPTH_PERCENT:
            return None

        sources = {"CONSOLIDATION_CEILING"}
        if cls._structure_value(price_structure, "flat_base") is True:
            sources.add("FLAT_BASE_RESISTANCE")
        if cls._structure_value(price_structure, "support_compression") is True:
            sources.add("VCP_COMPATIBLE_PIVOT")
        return {
            "level": level,
            "sources": sources,
            "test_count": test_count,
            "age": int(len(window) - 1 - touches.index.max()),
        }

    @classmethod
    def _merge_candidates(cls, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        for candidate in sorted(candidates, key=lambda item: item["level"]):
            target = next(
                (
                    item
                    for item in merged
                    if abs(candidate["level"] - median(item["levels"]))
                    / median(item["levels"])
                    * 100
                    <= PIVOT_RESISTANCE_TOLERANCE_PERCENT
                ),
                None,
            )
            if target is None:
                merged.append(
                    {
                        "levels": [candidate["level"]],
                        "sources": set(candidate["sources"]),
                        "test_count": candidate["test_count"],
                        "age": candidate["age"],
                    }
                )
            else:
                target["levels"].append(candidate["level"])
                target["sources"].update(candidate["sources"])
                target["test_count"] = max(
                    target["test_count"], candidate["test_count"]
                )
                target["age"] = min(target["age"], candidate["age"])

        normalized = []
        for item in merged:
            sources = sorted(
                item["sources"],
                key=lambda source: (-PIVOT_SOURCE_BASE_QUALITY[source], source),
            )
            normalized.append(
                {
                    "level": round(float(median(item["levels"])), 4),
                    "sources": sources,
                    "source": sources[0],
                    "test_count": int(item["test_count"]),
                    "age": int(item["age"]),
                }
            )
        return normalized

    @staticmethod
    def _quality(candidate: dict[str, Any], distance: float) -> int:
        score = PIVOT_SOURCE_BASE_QUALITY[candidate["source"]]
        score += min(max(candidate["test_count"] - 1, 0) * 4, 12)
        score += max(0, 8 - min(candidate["age"], 8))
        if len(candidate["sources"]) > 1:
            score += min((len(candidate["sources"]) - 1) * 4, 8)
        if abs(distance) <= PIVOT_NEAR_MAX_DISTANCE_PERCENT:
            score += 5
        return max(0, min(100, int(round(score))))

    @classmethod
    def extract(
        cls,
        frame: pd.DataFrame,
        *,
        current_price: float | None = None,
        price_structure: Any = None,
    ) -> PivotFeatures:
        result = PivotFeatures()
        if frame.empty:
            result.data_quality.extend(["MISSING_CANDLE_DATA", "PIVOT_NOT_DETERMINED"])
            return result
        if not cls.REQUIRED_COLUMNS.issubset(frame.columns):
            result.data_quality.extend(["PIVOT_DATA_UNAVAILABLE", "PIVOT_NOT_DETERMINED"])
            return result

        clean = frame.loc[:, ["high", "low", "close"]].apply(
            pd.to_numeric, errors="coerce"
        ).dropna()
        clean = clean.loc[
            (clean > 0).all(axis=1)
            & (clean["high"] >= clean[["low", "close"]].max(axis=1))
            & (clean["low"] <= clean[["high", "close"]].min(axis=1))
        ]
        if len(clean) < PIVOT_MIN_HISTORY:
            result.data_quality.extend(
                ["INSUFFICIENT_PIVOT_HISTORY", "PIVOT_NOT_DETERMINED"]
            )
            return result

        working = clean.tail(PIVOT_LOOKBACK).reset_index(drop=True)
        price = cls._number(current_price) or cls._number(working["close"].iloc[-1])
        if price is None:
            result.data_quality.extend(["CURRENT_PRICE_UNAVAILABLE", "PIVOT_NOT_DETERMINED"])
            return result

        swings = cls._swing_highs(working)
        candidates = cls._cluster_swings(swings)
        ceiling = cls._ceiling_candidate(working, price_structure)
        if ceiling is not None:
            candidates.append(ceiling)

        if swings:
            recent = min(swings, key=lambda item: (item["age"], -item["level"]))
            already_represented = any(
                abs(recent["level"] - candidate["level"]) / candidate["level"] * 100
                <= PIVOT_RESISTANCE_TOLERANCE_PERCENT
                for candidate in candidates
            )
            if not already_represented:
                candidates.append(
                    {
                        "level": recent["level"],
                        "sources": {"SWING_HIGH_RESISTANCE"},
                        "test_count": 1,
                        "age": recent["age"],
                    }
                )

        normalized = cls._merge_candidates(candidates)
        selectable = []
        for candidate in normalized:
            distance = cls._distance(candidate["level"], price)
            if distance < -PIVOT_MAX_BREACH_PERCENT:
                continue
            candidate["distance_to_breakout_pct"] = distance
            candidate["quality_score"] = cls._quality(candidate, distance)
            selectable.append(candidate)

        if not selectable:
            result.data_quality.append("PIVOT_NOT_DETERMINED")
            return result

        selectable.sort(
            key=lambda item: (
                -item["quality_score"],
                abs(item["distance_to_breakout_pct"]),
                -item["test_count"],
                item["level"],
                item["source"],
            )
        )
        selected = selectable[0]
        result.breakout_level = selected["level"]
        result.distance_to_breakout_pct = selected["distance_to_breakout_pct"]
        result.pivot_source = selected["source"]
        result.pivot_test_count = selected["test_count"]
        result.pivot_quality_score = selected["quality_score"]
        result.near_pivot = abs(result.distance_to_breakout_pct) <= PIVOT_NEAR_MAX_DISTANCE_PERCENT
        result.already_above_pivot = result.distance_to_breakout_pct < 0
        result.resistance_too_far = (
            result.distance_to_breakout_pct > PIVOT_TOO_FAR_DISTANCE_PERCENT
        )
        result.resistance_clustered = any(
            candidate["test_count"] >= PIVOT_MIN_RESISTANCE_TESTS
            for candidate in selectable
        )
        result.pivot_candidates = [
            {
                "level": candidate["level"],
                "source": candidate["source"],
                "sources": candidate["sources"],
                "test_count": candidate["test_count"],
                "quality_score": candidate["quality_score"],
                "distance_to_breakout_pct": candidate["distance_to_breakout_pct"],
            }
            for candidate in selectable
        ]
        result.pivot_candidate_count = len(result.pivot_candidates)

        result.pivot_reason_codes = [selected["source"]]
        if selected["source"] == "SWING_HIGH_RESISTANCE":
            result.pivot_reason_codes.append("RECENT_SIGNIFICANT_RESISTANCE")
        if result.pivot_test_count >= PIVOT_MIN_RESISTANCE_TESTS:
            result.pivot_reason_codes.append("REPEATED_RESISTANCE_TESTS")
        if result.resistance_clustered:
            result.pivot_reason_codes.append("RESISTANCE_CLUSTERING")
        if result.near_pivot:
            result.pivot_reason_codes.append("NEAR_PIVOT")
        if result.already_above_pivot:
            result.pivot_reason_codes.append("ALREADY_ABOVE_PIVOT")

        if result.pivot_quality_score < PIVOT_LOW_QUALITY_SCORE:
            result.pivot_quality_flags.append("LOW_PIVOT_CONFIDENCE")
        if result.pivot_test_count < PIVOT_MIN_RESISTANCE_TESTS:
            result.pivot_quality_flags.append("SINGLE_TEST_PIVOT")
        if result.already_above_pivot:
            result.pivot_quality_flags.append("PIVOT_ALREADY_BREACHED")
        if result.resistance_too_far:
            result.pivot_quality_flags.append("PIVOT_TOO_FAR")
        return result


pivot_feature_extractor = PivotFeatureExtractor()
