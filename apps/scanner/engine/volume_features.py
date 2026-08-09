from __future__ import annotations

from dataclasses import asdict, dataclass, field
from math import isfinite
from typing import Any

import pandas as pd

from .prebreakout_config import (
    ACCUMULATION_LOOKBACK,
    ACCUMULATION_MIN_DAYS,
    AVERAGE_VOLUME_LONG_LOOKBACK,
    AVERAGE_VOLUME_SHORT_LOOKBACK,
    POCKET_PIVOT_LOOKBACK,
    POCKET_PIVOT_MIN_CLOSE_LOCATION,
    POCKET_PIVOT_MIN_DOWN_DAYS,
    POCKET_PIVOT_MIN_RVOL,
    UP_DOWN_VOLUME_LOOKBACK,
    UP_VOLUME_DOMINANCE_MIN_RATIO,
    VOLUME_CONSOLIDATION_BASELINE_LOOKBACK,
    VOLUME_CONSOLIDATION_LOOKBACK,
    VOLUME_CONSOLIDATION_MAX_PRICE_RANGE_PERCENT,
    VOLUME_CONSOLIDATION_MAX_RATIO,
    VOLUME_DRY_UP_BASELINE_LOOKBACK,
    VOLUME_DRY_UP_MAX_RATIO,
    VOLUME_DRY_UP_RECENT_LOOKBACK,
    VOLUME_EXPANSION_MIN_RVOL,
    VOLUME_MIN_HISTORY,
)


@dataclass(slots=True)
class VolumeFeatures:
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
    data_quality: list[str] = field(default_factory=list)

    def as_mapping(self) -> dict[str, Any]:
        return asdict(self)


class VolumeFeatureExtractor:
    """Deterministic volume features derived from daily OHLCV candles.

    RVOL is the latest candle's volume divided by the mean volume of the
    previous 20 completed candles. The latest candle is deliberately excluded
    from the denominator so a large current day cannot inflate its own base.
    """

    REQUIRED_COLUMNS = frozenset({"high", "low", "close", "volume", "ema_10"})

    @staticmethod
    def _number(value: Any) -> float | None:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed if isfinite(parsed) else None

    @classmethod
    def _mean(cls, series: pd.Series) -> float | None:
        values = pd.to_numeric(series, errors="coerce").dropna()
        if values.empty:
            return None
        return cls._number(values.mean())

    @staticmethod
    def _ratio(numerator: float | None, denominator: float | None) -> float | None:
        if numerator is None or denominator is None or denominator <= 0:
            return None
        return round(numerator / denominator, 4)

    @staticmethod
    def _rounded(value: float | None) -> float | None:
        return round(value, 2) if value is not None else None

    @classmethod
    def extract(cls, frame: pd.DataFrame) -> VolumeFeatures:
        result = VolumeFeatures()

        if frame.empty:
            result.data_quality.extend(
                ["MISSING_CANDLE_DATA", "VOLUME_DATA_UNAVAILABLE"]
            )
            return result

        missing = cls.REQUIRED_COLUMNS.difference(frame.columns)
        if missing:
            result.data_quality.append("VOLUME_DATA_UNAVAILABLE")

        if "volume" not in frame.columns:
            return result

        volumes = pd.to_numeric(frame["volume"], errors="coerce")
        valid_volume_count = int(volumes.notna().sum())
        if valid_volume_count == 0:
            result.data_quality.append("VOLUME_DATA_UNAVAILABLE")
            return result

        if len(frame) < VOLUME_MIN_HISTORY:
            result.data_quality.append("INSUFFICIENT_VOLUME_HISTORY")

        current_volume = cls._number(volumes.iloc[-1])
        if current_volume is None:
            result.data_quality.append("VOLUME_DATA_UNAVAILABLE")
            return result

        for lookback, average_field, ratio_field in (
            (5, "avg_volume_5", "volume_ratio_5d"),
            (10, "avg_volume_10", "volume_ratio_10d"),
            (20, "avg_volume_20", "volume_ratio_20d"),
            (50, "avg_volume_50", "volume_ratio_50d"),
        ):
            if len(frame) >= lookback + 1:
                average = cls._mean(volumes.iloc[-(lookback + 1):-1])
                setattr(result, average_field, cls._rounded(average))
                setattr(result, ratio_field, cls._ratio(current_volume, average))

        recent_50 = volumes.tail(50)
        if not recent_50.empty:
            result.zero_volume_ratio_50d = round(
                float((recent_50 == 0).sum()) / len(recent_50), 4
            )
            positive = recent_50.loc[recent_50 > 0]
            if not positive.empty:
                median = cls._number(positive.median())
                result.abnormal_volume = bool(
                    median is not None and median > 0
                    and current_volume > median * 50
                )

        if len(frame) >= AVERAGE_VOLUME_SHORT_LOOKBACK + 1:
            avg_20 = cls._mean(
                volumes.iloc[-(AVERAGE_VOLUME_SHORT_LOOKBACK + 1):-1]
            )
            result.avg_volume_20 = cls._rounded(avg_20)
            result.rvol = cls._ratio(current_volume, avg_20)
            result.volume_ratio_20d = result.rvol
            if result.rvol is not None:
                result.volume_expansion = result.rvol >= VOLUME_EXPANSION_MIN_RVOL

        if len(frame) >= AVERAGE_VOLUME_LONG_LOOKBACK + 1:
            result.avg_volume_50 = cls._rounded(
                cls._mean(volumes.iloc[-(AVERAGE_VOLUME_LONG_LOOKBACK + 1):-1])
            )

        dry_up_required = VOLUME_DRY_UP_RECENT_LOOKBACK + VOLUME_DRY_UP_BASELINE_LOOKBACK
        if len(frame) >= dry_up_required:
            recent_volume = cls._mean(volumes.iloc[-VOLUME_DRY_UP_RECENT_LOOKBACK:])
            baseline_volume = cls._mean(
                volumes.iloc[-dry_up_required:-VOLUME_DRY_UP_RECENT_LOOKBACK]
            )
            result.volume_dry_up_ratio = cls._ratio(recent_volume, baseline_volume)
            if result.volume_dry_up_ratio is not None:
                result.volume_dry_up = (
                    result.volume_dry_up_ratio <= VOLUME_DRY_UP_MAX_RATIO
                )

        consolidation_required = (
            VOLUME_CONSOLIDATION_LOOKBACK
            + VOLUME_CONSOLIDATION_BASELINE_LOOKBACK
        )
        if (
            len(frame) >= consolidation_required
            and {"high", "low", "close"}.issubset(frame.columns)
        ):
            recent = frame.iloc[-VOLUME_CONSOLIDATION_LOOKBACK:]
            recent_volume = cls._mean(recent["volume"])
            baseline_volume = cls._mean(
                volumes.iloc[
                    -consolidation_required:-VOLUME_CONSOLIDATION_LOOKBACK
                ]
            )
            result.consolidation_volume_ratio = cls._ratio(
                recent_volume, baseline_volume
            )
            recent_high = cls._number(
                pd.to_numeric(recent["high"], errors="coerce").max()
            )
            recent_low = cls._number(
                pd.to_numeric(recent["low"], errors="coerce").min()
            )
            current_close = cls._number(recent["close"].iloc[-1])
            price_range_pct = None
            if (
                recent_high is not None
                and recent_low is not None
                and current_close is not None
                and current_close > 0
            ):
                price_range_pct = ((recent_high - recent_low) / current_close) * 100

            if result.consolidation_volume_ratio is not None and price_range_pct is not None:
                result.volume_contracting_in_consolidation = (
                    result.consolidation_volume_ratio
                    <= VOLUME_CONSOLIDATION_MAX_RATIO
                    and price_range_pct
                    <= VOLUME_CONSOLIDATION_MAX_PRICE_RANGE_PERCENT
                )

        if len(frame) >= UP_DOWN_VOLUME_LOOKBACK + 1 and "close" in frame.columns:
            closes = pd.to_numeric(frame["close"], errors="coerce")
            window = frame.tail(UP_DOWN_VOLUME_LOOKBACK + 1).copy()
            window_close = pd.to_numeric(window["close"], errors="coerce")
            window_volume = pd.to_numeric(window["volume"], errors="coerce")
            changes = window_close.diff()
            up_volume = cls._number(window_volume.where(changes > 0).sum(min_count=1))
            down_volume = cls._number(window_volume.where(changes < 0).sum(min_count=1))
            result.up_volume = cls._rounded(up_volume)
            result.down_volume = cls._rounded(down_volume)
            result.up_down_volume_ratio = cls._ratio(up_volume, down_volume)
            if result.up_down_volume_ratio is not None:
                result.up_volume_dominant = (
                    result.up_down_volume_ratio >= UP_VOLUME_DOMINANCE_MIN_RATIO
                )

            rolling_average = volumes.shift(1).rolling(
                AVERAGE_VOLUME_SHORT_LOOKBACK,
                min_periods=AVERAGE_VOLUME_SHORT_LOOKBACK,
            ).mean()
            price_changes = closes.diff()
            accumulation_mask = (price_changes > 0) & (volumes > rolling_average)
            distribution_mask = (price_changes < 0) & (volumes > rolling_average)
            result.accumulation_days = int(
                accumulation_mask.tail(ACCUMULATION_LOOKBACK).sum()
            )
            result.distribution_days = int(
                distribution_mask.tail(ACCUMULATION_LOOKBACK).sum()
            )
            result.accumulation_behavior = (
                result.accumulation_days >= ACCUMULATION_MIN_DAYS
                and result.accumulation_days > result.distribution_days
                and result.up_volume_dominant is True
            )

        if (
            len(frame) >= max(AVERAGE_VOLUME_SHORT_LOOKBACK + 1, POCKET_PIVOT_LOOKBACK + 1)
            and {"high", "low", "close", "ema_10"}.issubset(frame.columns)
        ):
            current = frame.iloc[-1]
            previous = frame.iloc[-(POCKET_PIVOT_LOOKBACK + 1):-1]
            previous_closes = pd.to_numeric(previous["close"], errors="coerce")
            prior_closes = pd.to_numeric(
                frame["close"].iloc[-(POCKET_PIVOT_LOOKBACK + 2):-2],
                errors="coerce",
            )
            down_mask = previous_closes.to_numpy() < prior_closes.to_numpy()
            previous_volumes = pd.to_numeric(previous["volume"], errors="coerce")
            down_volumes = previous_volumes[down_mask].dropna()

            current_close = cls._number(current["close"])
            previous_close = cls._number(frame["close"].iloc[-2])
            current_high = cls._number(current["high"])
            current_low = cls._number(current["low"])
            current_ema_10 = cls._number(current["ema_10"])
            close_location = None
            if (
                current_close is not None
                and current_high is not None
                and current_low is not None
                and current_high > current_low
            ):
                close_location = (current_close - current_low) / (
                    current_high - current_low
                )

            result.pocket_pivot_style = bool(
                len(down_volumes) >= POCKET_PIVOT_MIN_DOWN_DAYS
                and current_close is not None
                and previous_close is not None
                and current_close > previous_close
                and current_ema_10 is not None
                and current_close >= current_ema_10
                and result.rvol is not None
                and result.rvol >= POCKET_PIVOT_MIN_RVOL
                and current_volume > float(down_volumes.max())
                and close_location is not None
                and close_location >= POCKET_PIVOT_MIN_CLOSE_LOCATION
            )

        reason_pairs = (
            (result.volume_dry_up, "VOLUME_DRY_UP"),
            (
                result.volume_contracting_in_consolidation,
                "CONSOLIDATION_VOLUME_CONTRACTION",
            ),
            (result.up_volume_dominant, "UP_VOLUME_DOMINANT"),
            (result.accumulation_behavior, "ACCUMULATION_BEHAVIOUR"),
            (result.volume_expansion, "VOLUME_EXPANSION"),
            (result.pocket_pivot_style, "POCKET_PIVOT_STYLE"),
            (result.abnormal_volume, "ABNORMAL_VOLUME"),
        )
        result.volume_reason_codes = [
            code for detected, code in reason_pairs if detected is True
        ]
        result.data_quality = list(dict.fromkeys(result.data_quality))
        return result


volume_feature_extractor = VolumeFeatureExtractor()
