from __future__ import annotations

from dataclasses import asdict, dataclass, field
from math import isfinite
from typing import Any

import pandas as pd

from .prebreakout_config import (
    ASCENDING_TRIANGLE_MAX_DEPTH_PERCENT,
    DARVAS_BOX_BOUNDARY_TOLERANCE_PERCENT,
    DARVAS_BOX_FORMATION_PERIOD,
    DARVAS_BOX_LOOKBACK,
    DARVAS_BOX_MAX_DEPTH_PERCENT,
    DARVAS_BOX_MIN_BOUNDARY_TESTS,
    FLAT_BASE_MAX_DEPTH_PERCENT,
    HIGHER_LOW_MIN_RISE_PERCENT,
    HIGHER_LOW_MIN_SWINGS,
    INSIDE_BAR_LOOKBACK,
    MULTIPLE_TIGHT_CLOSE_LOOKBACK,
    MULTIPLE_TIGHT_CLOSE_MAX_RANGE_PERCENT,
    MULTIPLE_TIGHT_CLOSE_MIN_TRANSITIONS,
    PRICE_STRUCTURE_MIN_HISTORY,
    RESISTANCE_CLUSTER_MIN_TESTS,
    RESISTANCE_CLUSTER_TOLERANCE_PERCENT,
    RESISTANCE_PROXIMITY_MAX_PERCENT,
    STRUCTURE_LOOKBACK,
    SUPPORT_COMPRESSION_BASELINE_LOOKBACK,
    SUPPORT_COMPRESSION_MAX_RANGE_RATIO,
    SUPPORT_COMPRESSION_RECENT_LOOKBACK,
    SWING_MIN_SEPARATION,
    SWING_WINDOW,
    TIGHT_CLOSE_LOOKBACK,
    TIGHT_CLOSE_MAX_DAILY_CHANGE_PERCENT,
    TIGHT_CLOSE_MAX_RANGE_PERCENT,
)


@dataclass(slots=True)
class PriceStructureFeatures:
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
    data_quality: list[str] = field(default_factory=list)

    def as_mapping(self) -> dict[str, Any]:
        return asdict(self)


class PriceStructureFeatureExtractor:
    """Objective price-structure rules; does not select a breakout pivot."""

    REQUIRED_COLUMNS = frozenset({"high", "low", "close"})

    @staticmethod
    def _number(value: Any) -> float | None:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed if isfinite(parsed) else None

    @classmethod
    def _range_percent(cls, values: pd.Series) -> float | None:
        numeric = pd.to_numeric(values, errors="coerce").dropna()
        if numeric.empty:
            return None
        center = cls._number(numeric.mean())
        if center is None or center <= 0:
            return None
        return round(float((numeric.max() - numeric.min()) / center * 100), 4)

    @classmethod
    def _swing_lows(cls, lows: pd.Series) -> list[tuple[int, float]]:
        numeric = pd.to_numeric(lows, errors="coerce").reset_index(drop=True)
        candidates: list[tuple[int, float]] = []
        for index in range(SWING_WINDOW, len(numeric) - SWING_WINDOW):
            value = cls._number(numeric.iloc[index])
            if value is None:
                continue
            left = numeric.iloc[index - SWING_WINDOW:index]
            right = numeric.iloc[index + 1:index + SWING_WINDOW + 1]
            if value < left.min() and value <= right.min():
                if candidates and index - candidates[-1][0] < SWING_MIN_SEPARATION:
                    if value < candidates[-1][1]:
                        candidates[-1] = (index, value)
                    continue
                candidates.append((index, value))
        return candidates

    @staticmethod
    def _higher_lows(swings: list[tuple[int, float]]) -> bool | None:
        if len(swings) < HIGHER_LOW_MIN_SWINGS:
            return None
        recent = [value for _, value in swings[-HIGHER_LOW_MIN_SWINGS:]]
        return all(
            current >= previous * (1 + HIGHER_LOW_MIN_RISE_PERCENT / 100)
            for previous, current in zip(recent, recent[1:])
        )

    @classmethod
    def extract(cls, frame: pd.DataFrame) -> PriceStructureFeatures:
        result = PriceStructureFeatures()
        if frame.empty:
            result.data_quality.extend(
                ["MISSING_CANDLE_DATA", "INSUFFICIENT_PRICE_STRUCTURE_HISTORY"]
            )
            return result

        if not cls.REQUIRED_COLUMNS.issubset(frame.columns):
            result.data_quality.append("PRICE_STRUCTURE_DATA_UNAVAILABLE")
            return result

        clean = frame.loc[:, ["high", "low", "close"]].apply(
            pd.to_numeric, errors="coerce"
        )
        if clean.isna().any(axis=None):
            result.data_quality.append("PRICE_STRUCTURE_DATA_UNAVAILABLE")
            clean = clean.dropna()
        if clean.empty:
            return result

        if len(clean) < PRICE_STRUCTURE_MIN_HISTORY:
            result.data_quality.append("INSUFFICIENT_PRICE_STRUCTURE_HISTORY")

        structure = clean.tail(STRUCTURE_LOOKBACK).reset_index(drop=True)
        swings = cls._swing_lows(structure["low"])
        result.swing_low_count = len(swings)
        result.higher_lows = cls._higher_lows(swings)

        if len(clean) >= TIGHT_CLOSE_LOOKBACK:
            result.tight_close_range_pct = cls._range_percent(
                clean["close"].tail(TIGHT_CLOSE_LOOKBACK)
            )
            if result.tight_close_range_pct is not None:
                result.tight_closes = (
                    result.tight_close_range_pct <= TIGHT_CLOSE_MAX_RANGE_PERCENT
                )

        if len(clean) >= MULTIPLE_TIGHT_CLOSE_LOOKBACK:
            close_window = clean["close"].tail(MULTIPLE_TIGHT_CLOSE_LOOKBACK)
            multiple_range = cls._range_percent(close_window)
            daily_changes = close_window.pct_change().abs() * 100
            result.tight_close_transition_count = int(
                (daily_changes <= TIGHT_CLOSE_MAX_DAILY_CHANGE_PERCENT).sum()
            )
            result.multiple_tight_closes = bool(
                multiple_range is not None
                and multiple_range <= MULTIPLE_TIGHT_CLOSE_MAX_RANGE_PERCENT
                and result.tight_close_transition_count
                >= MULTIPLE_TIGHT_CLOSE_MIN_TRANSITIONS
            )

        if len(clean) >= 2:
            current = clean.iloc[-1]
            previous = clean.iloc[-2]
            result.inside_bar = bool(
                current["high"] <= previous["high"]
                and current["low"] >= previous["low"]
            )
            recent_inside = clean.tail(INSIDE_BAR_LOOKBACK + 1)
            inside_count = 0
            for index in range(1, len(recent_inside)):
                bar = recent_inside.iloc[index]
                prior = recent_inside.iloc[index - 1]
                if bar["high"] <= prior["high"] and bar["low"] >= prior["low"]:
                    inside_count += 1
            result.inside_bar_count = inside_count

        compression_required = (
            SUPPORT_COMPRESSION_RECENT_LOOKBACK
            + SUPPORT_COMPRESSION_BASELINE_LOOKBACK
        )
        if len(clean) >= compression_required:
            candle_ranges = clean["high"] - clean["low"]
            recent_mean = cls._number(
                candle_ranges.tail(SUPPORT_COMPRESSION_RECENT_LOOKBACK).mean()
            )
            baseline_mean = cls._number(
                candle_ranges.iloc[
                    -compression_required:-SUPPORT_COMPRESSION_RECENT_LOOKBACK
                ].mean()
            )
            if recent_mean is not None and baseline_mean is not None and baseline_mean > 0:
                result.support_range_contraction_ratio = round(
                    recent_mean / baseline_mean, 4
                )
                result.support_compression = bool(
                    result.higher_lows is True
                    and result.support_range_contraction_ratio
                    <= SUPPORT_COMPRESSION_MAX_RANGE_RATIO
                )

        if len(structure) >= RESISTANCE_CLUSTER_MIN_TESTS:
            resistance_reference = cls._number(structure["high"].max())
            current_close = cls._number(structure["close"].iloc[-1])
            if resistance_reference is not None and resistance_reference > 0:
                tolerance = resistance_reference * (
                    RESISTANCE_CLUSTER_TOLERANCE_PERCENT / 100
                )
                clustered_highs = structure.loc[
                    structure["high"] >= resistance_reference - tolerance,
                    "high",
                ]
                result.resistance_cluster_test_count = len(clustered_highs)
                result.resistance_cluster_spread_pct = cls._range_percent(
                    clustered_highs
                )
                proximity = None
                if current_close is not None and current_close > 0:
                    proximity = (
                        (resistance_reference - current_close) / current_close * 100
                    )
                result.price_clustered_near_resistance = bool(
                    len(clustered_highs) >= RESISTANCE_CLUSTER_MIN_TESTS
                    and proximity is not None
                    and 0 <= proximity <= RESISTANCE_PROXIMITY_MAX_PERCENT
                )

                structure_low = cls._number(structure["low"].min())
                depth = None
                if structure_low is not None:
                    depth = (
                        (resistance_reference - structure_low)
                        / resistance_reference
                        * 100
                    )
                    result.flat_base_depth_pct = round(depth, 4)

                flat_resistance = bool(
                    len(clustered_highs) >= RESISTANCE_CLUSTER_MIN_TESTS
                    and result.resistance_cluster_spread_pct is not None
                    and result.resistance_cluster_spread_pct
                    <= RESISTANCE_CLUSTER_TOLERANCE_PERCENT
                )
                result.flat_base = bool(
                    depth is not None
                    and depth <= FLAT_BASE_MAX_DEPTH_PERCENT
                    and flat_resistance
                    and result.price_clustered_near_resistance is True
                )
                result.ascending_triangle = bool(
                    depth is not None
                    and depth <= ASCENDING_TRIANGLE_MAX_DEPTH_PERCENT
                    and flat_resistance
                    and result.higher_lows is True
                    and result.price_clustered_near_resistance is True
                )

        if len(clean) >= DARVAS_BOX_LOOKBACK:
            box_window = clean.tail(DARVAS_BOX_LOOKBACK).reset_index(drop=True)
            formation = box_window.head(DARVAS_BOX_FORMATION_PERIOD)
            confirmation = box_window.tail(
                DARVAS_BOX_LOOKBACK - DARVAS_BOX_FORMATION_PERIOD
            )
            box_high = cls._number(formation["high"].quantile(0.90))
            box_low = cls._number(formation["low"].quantile(0.10))
            if box_high is not None and box_low is not None and box_high > box_low > 0:
                depth = (box_high - box_low) / box_high * 100
                result.darvas_box_depth_pct = round(depth, 4)
                high_tolerance = box_high * DARVAS_BOX_BOUNDARY_TOLERANCE_PERCENT / 100
                low_tolerance = box_low * DARVAS_BOX_BOUNDARY_TOLERANCE_PERCENT / 100
                top_tests = int((formation["high"] >= box_high - high_tolerance).sum())
                bottom_tests = int((formation["low"] <= box_low + low_tolerance).sum())
                contained = bool(
                    (confirmation["high"] <= box_high + high_tolerance).all()
                    and (confirmation["low"] >= box_low - low_tolerance).all()
                )
                result.darvas_consolidation = bool(
                    depth <= DARVAS_BOX_MAX_DEPTH_PERCENT
                    and top_tests >= DARVAS_BOX_MIN_BOUNDARY_TESTS
                    and bottom_tests >= DARVAS_BOX_MIN_BOUNDARY_TESTS
                    and contained
                )

        reason_pairs = (
            (result.higher_lows, "HIGHER_LOWS"),
            (result.tight_closes, "TIGHT_CLOSES"),
            (result.multiple_tight_closes, "MULTIPLE_TIGHT_CLOSES"),
            (result.inside_bar, "INSIDE_BAR"),
            (result.support_compression, "SUPPORT_COMPRESSION"),
            (
                result.price_clustered_near_resistance,
                "PRICE_CLUSTERED_NEAR_RESISTANCE",
            ),
            (result.flat_base, "FLAT_BASE"),
            (result.ascending_triangle, "ASCENDING_TRIANGLE"),
            (result.darvas_consolidation, "DARVAS_CONSOLIDATION"),
        )
        result.price_structure_reason_codes = [
            code for detected, code in reason_pairs if detected is True
        ]
        result.data_quality = list(dict.fromkeys(result.data_quality))
        return result


price_structure_feature_extractor = PriceStructureFeatureExtractor()
