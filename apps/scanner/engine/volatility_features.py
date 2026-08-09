from __future__ import annotations

from dataclasses import asdict, dataclass, field
from math import isfinite
from typing import Any

import pandas as pd

from .prebreakout_config import (
    ATR_CONTRACTION_BASELINE_LOOKBACK,
    ATR_CONTRACTION_MAX_RATIO,
    ATR_CONTRACTION_RECENT_LOOKBACK,
    BOLLINGER_SQUEEZE_LOOKBACK,
    BOLLINGER_SQUEEZE_MIN_HISTORY,
    BOLLINGER_SQUEEZE_QUANTILE,
    CANDLE_RANGE_BASELINE_LOOKBACK,
    CANDLE_RANGE_CONTRACTION_MAX_RATIO,
    CANDLE_RANGE_RECENT_LOOKBACK,
    ROLLING_RANGE_CONTRACTION_MAX_RATIO,
    ROLLING_RANGE_LOOKBACK,
    ROLLING_RANGE_MAX_PERCENT,
    STDDEV_BASELINE_LOOKBACK,
    STDDEV_CONTRACTION_MAX_RATIO,
    STDDEV_RECENT_LOOKBACK,
    VOLATILITY_MIN_HISTORY,
)


@dataclass(slots=True)
class VolatilityFeatures:
    atr_pct: float | None = None
    atr_contraction_ratio: float | None = None
    atr_contracting: bool | None = None
    bb_width_pct: float | None = None
    bb_width_percentile: float | None = None
    bollinger_squeeze: bool | None = None
    nr4: bool | None = None
    nr7: bool | None = None
    rolling_range_pct: float | None = None
    rolling_range_contraction_ratio: float | None = None
    rolling_range_compressed: bool | None = None
    candle_range_contraction_ratio: float | None = None
    candle_range_contracting: bool | None = None
    stddev_contraction_ratio: float | None = None
    stddev_contracting: bool | None = None
    volatility_reason_codes: list[str] = field(default_factory=list)
    data_quality: list[str] = field(default_factory=list)

    def as_mapping(self) -> dict[str, Any]:
        return asdict(self)


class VolatilityFeatureExtractor:
    """Derives contraction features from existing ATR/Bollinger calculations."""

    REQUIRED_COLUMNS = frozenset(
        {"high", "low", "close", "atr", "bb_middle", "bb_width"}
    )

    @staticmethod
    def _number(value: Any) -> float | None:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed if isfinite(parsed) else None

    @classmethod
    def _latest(cls, frame: pd.DataFrame, column: str) -> float | None:
        if frame.empty or column not in frame.columns:
            return None
        return cls._number(frame[column].iloc[-1])

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
        return round(value, 4) if value is not None else None

    @classmethod
    def extract(cls, frame: pd.DataFrame) -> VolatilityFeatures:
        result = VolatilityFeatures()

        if frame.empty:
            result.data_quality.extend(
                ["MISSING_CANDLE_DATA", "INSUFFICIENT_VOLATILITY_HISTORY"]
            )
            return result

        missing = cls.REQUIRED_COLUMNS.difference(frame.columns)
        if missing:
            result.data_quality.append("MISSING_VOLATILITY_INDICATOR_DATA")

        if len(frame) < VOLATILITY_MIN_HISTORY:
            result.data_quality.append("INSUFFICIENT_VOLATILITY_HISTORY")

        close = cls._latest(frame, "close")
        atr = cls._latest(frame, "atr")
        if close is not None and close > 0 and atr is not None:
            result.atr_pct = cls._rounded((atr / close) * 100)
        else:
            result.data_quality.append("ATR_DATA_UNAVAILABLE")

        atr_required = (
            ATR_CONTRACTION_RECENT_LOOKBACK + ATR_CONTRACTION_BASELINE_LOOKBACK
        )
        if "atr" in frame.columns and len(frame) >= atr_required:
            recent_atr = cls._mean(frame["atr"].iloc[-ATR_CONTRACTION_RECENT_LOOKBACK:])
            baseline_atr = cls._mean(
                frame["atr"].iloc[
                    -atr_required:-ATR_CONTRACTION_RECENT_LOOKBACK
                ]
            )
            result.atr_contraction_ratio = cls._ratio(recent_atr, baseline_atr)
            if result.atr_contraction_ratio is not None:
                result.atr_contracting = (
                    result.atr_contraction_ratio <= ATR_CONTRACTION_MAX_RATIO
                )

        bb_middle = cls._latest(frame, "bb_middle")
        bb_width = cls._latest(frame, "bb_width")
        if bb_middle is not None and bb_middle > 0 and bb_width is not None:
            result.bb_width_pct = cls._rounded((bb_width / bb_middle) * 100)
        else:
            result.data_quality.append("BOLLINGER_DATA_UNAVAILABLE")

        if {"bb_middle", "bb_width"}.issubset(frame.columns):
            middle = pd.to_numeric(frame["bb_middle"], errors="coerce")
            width = pd.to_numeric(frame["bb_width"], errors="coerce")
            width_pct = ((width / middle.where(middle > 0)) * 100).dropna().tail(
                BOLLINGER_SQUEEZE_LOOKBACK
            )
            if len(width_pct) >= BOLLINGER_SQUEEZE_MIN_HISTORY:
                current_width = cls._number(width_pct.iloc[-1])
                threshold = cls._number(width_pct.quantile(BOLLINGER_SQUEEZE_QUANTILE))
                if current_width is not None and threshold is not None:
                    result.bb_width_percentile = cls._rounded(
                        float((width_pct <= current_width).mean() * 100)
                    )
                    result.bollinger_squeeze = current_width <= threshold
            elif "BOLLINGER_DATA_UNAVAILABLE" not in result.data_quality:
                result.data_quality.append("BOLLINGER_SQUEEZE_HISTORY_INSUFFICIENT")

        if {"high", "low"}.issubset(frame.columns):
            candle_ranges = (
                pd.to_numeric(frame["high"], errors="coerce")
                - pd.to_numeric(frame["low"], errors="coerce")
            )
            valid_ranges = candle_ranges.dropna()
            if len(valid_ranges) >= 4:
                result.nr4 = bool(valid_ranges.iloc[-1] <= valid_ranges.tail(4).min())
            if len(valid_ranges) >= 7:
                result.nr7 = bool(valid_ranges.iloc[-1] <= valid_ranges.tail(7).min())

            range_required = ROLLING_RANGE_LOOKBACK * 2
            if len(frame) >= range_required and close is not None and close > 0:
                recent = frame.iloc[-ROLLING_RANGE_LOOKBACK:]
                previous = frame.iloc[-range_required:-ROLLING_RANGE_LOOKBACK]
                recent_range = cls._number(
                    pd.to_numeric(recent["high"], errors="coerce").max()
                    - pd.to_numeric(recent["low"], errors="coerce").min()
                )
                previous_range = cls._number(
                    pd.to_numeric(previous["high"], errors="coerce").max()
                    - pd.to_numeric(previous["low"], errors="coerce").min()
                )
                if recent_range is not None:
                    result.rolling_range_pct = cls._rounded((recent_range / close) * 100)
                result.rolling_range_contraction_ratio = cls._ratio(
                    recent_range, previous_range
                )
                if (
                    result.rolling_range_pct is not None
                    and result.rolling_range_contraction_ratio is not None
                ):
                    result.rolling_range_compressed = (
                        result.rolling_range_pct <= ROLLING_RANGE_MAX_PERCENT
                        and result.rolling_range_contraction_ratio
                        <= ROLLING_RANGE_CONTRACTION_MAX_RATIO
                    )

            candle_required = (
                CANDLE_RANGE_RECENT_LOOKBACK + CANDLE_RANGE_BASELINE_LOOKBACK
            )
            if len(valid_ranges) >= candle_required:
                recent_mean = cls._mean(
                    valid_ranges.iloc[-CANDLE_RANGE_RECENT_LOOKBACK:]
                )
                baseline_mean = cls._mean(
                    valid_ranges.iloc[
                        -candle_required:-CANDLE_RANGE_RECENT_LOOKBACK
                    ]
                )
                result.candle_range_contraction_ratio = cls._ratio(
                    recent_mean, baseline_mean
                )
                if result.candle_range_contraction_ratio is not None:
                    result.candle_range_contracting = (
                        result.candle_range_contraction_ratio
                        <= CANDLE_RANGE_CONTRACTION_MAX_RATIO
                    )

        stddev_required = STDDEV_RECENT_LOOKBACK + STDDEV_BASELINE_LOOKBACK
        if "close" in frame.columns and len(frame) >= stddev_required:
            closes = pd.to_numeric(frame["close"], errors="coerce")
            recent_std = cls._number(closes.iloc[-STDDEV_RECENT_LOOKBACK:].std())
            baseline_std = cls._number(
                closes.iloc[-stddev_required:-STDDEV_RECENT_LOOKBACK].std()
            )
            result.stddev_contraction_ratio = cls._ratio(recent_std, baseline_std)
            if result.stddev_contraction_ratio is not None:
                result.stddev_contracting = (
                    result.stddev_contraction_ratio <= STDDEV_CONTRACTION_MAX_RATIO
                )

        reason_pairs = (
            (result.atr_contracting, "ATR_CONTRACTING"),
            (result.bollinger_squeeze, "BOLLINGER_SQUEEZE"),
            (result.nr4, "NR4"),
            (result.nr7, "NR7"),
            (result.rolling_range_compressed, "ROLLING_RANGE_COMPRESSED"),
            (result.candle_range_contracting, "CANDLE_RANGE_CONTRACTING"),
            (result.stddev_contracting, "STDDEV_CONTRACTING"),
        )
        result.volatility_reason_codes = [
            code for detected, code in reason_pairs if detected is True
        ]
        result.data_quality = list(dict.fromkeys(result.data_quality))
        return result


volatility_feature_extractor = VolatilityFeatureExtractor()
