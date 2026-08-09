from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import pandas as pd


@dataclass(slots=True)
class WeeklyFeatures:
    weekly_observations: int = 0
    weekly_trend: str | None = None
    weekly_close: float | None = None
    weekly_sma_10: float | None = None
    weekly_sma_30: float | None = None
    weekly_sma_40: float | None = None
    weekly_ma_alignment: bool | None = None
    weekly_price_structure: str | None = None
    weekly_contraction_ratio: float | None = None
    weekly_contraction: bool | None = None
    daily_weekly_alignment: bool | None = None
    weekly_reason_codes: list[str] = field(default_factory=list)
    weekly_data_quality: list[str] = field(default_factory=list)

    def as_mapping(self) -> dict[str, Any]:
        return asdict(self)


class WeeklyFeatureExtractor:
    """Derive weekly evidence exclusively from legitimate stored daily candles."""

    MIN_WEEKS = 40

    @staticmethod
    def _weekly(frame: pd.DataFrame) -> pd.DataFrame:
        required = {"timestamp", "open", "high", "low", "close", "volume"}
        if frame.empty or not required.issubset(frame.columns):
            return pd.DataFrame()
        prepared = frame.loc[:, list(required)].copy()
        prepared["timestamp"] = pd.to_datetime(
            prepared["timestamp"], errors="coerce", utc=True
        ).dt.tz_convert("Asia/Kolkata")
        for column in ("open", "high", "low", "close", "volume"):
            prepared[column] = pd.to_numeric(prepared[column], errors="coerce")
        prepared = prepared.dropna().sort_values("timestamp")
        if prepared.empty:
            return pd.DataFrame()
        return (
            prepared.set_index("timestamp")
            .resample("W-FRI", label="right", closed="right")
            .agg(
                open=("open", "first"),
                high=("high", "max"),
                low=("low", "min"),
                close=("close", "last"),
                volume=("volume", "sum"),
                sessions=("close", "count"),
            )
            .dropna(subset=["open", "high", "low", "close"])
        )

    @classmethod
    def extract(cls, frame: pd.DataFrame) -> WeeklyFeatures:
        result = WeeklyFeatures()
        weekly = cls._weekly(frame)
        if weekly.empty:
            result.weekly_data_quality.append("WEEKLY_DATA_UNAVAILABLE")
            return result

        result.weekly_observations = len(weekly)
        if len(weekly) < cls.MIN_WEEKS:
            result.weekly_data_quality.append("INSUFFICIENT_WEEKLY_HISTORY")
            return result

        weekly = weekly.copy()
        weekly["sma_10"] = weekly["close"].rolling(10, min_periods=10).mean()
        weekly["sma_30"] = weekly["close"].rolling(30, min_periods=30).mean()
        weekly["sma_40"] = weekly["close"].rolling(40, min_periods=40).mean()
        latest = weekly.iloc[-1]
        result.weekly_close = round(float(latest["close"]), 4)
        result.weekly_sma_10 = round(float(latest["sma_10"]), 4)
        result.weekly_sma_30 = round(float(latest["sma_30"]), 4)
        result.weekly_sma_40 = round(float(latest["sma_40"]), 4)
        result.weekly_ma_alignment = bool(
            result.weekly_close > result.weekly_sma_10
            > result.weekly_sma_30
            > result.weekly_sma_40
        )

        sma10_slope = float(weekly["sma_10"].iloc[-1] - weekly["sma_10"].iloc[-4])
        if result.weekly_ma_alignment and sma10_slope > 0:
            result.weekly_trend = "BULLISH"
        elif result.weekly_close < result.weekly_sma_30 and sma10_slope < 0:
            result.weekly_trend = "BEARISH"
        else:
            result.weekly_trend = "NEUTRAL"

        structure = weekly.tail(8)
        recent_highs = structure["high"].rolling(3).max().dropna()
        recent_lows = structure["low"].rolling(3).min().dropna()
        if len(recent_highs) >= 2 and len(recent_lows) >= 2:
            if recent_highs.iloc[-1] >= recent_highs.iloc[-2] and recent_lows.iloc[-1] > recent_lows.iloc[-2]:
                result.weekly_price_structure = "HIGHER_HIGHS_HIGHER_LOWS"
            elif recent_highs.iloc[-1] < recent_highs.iloc[-2] and recent_lows.iloc[-1] < recent_lows.iloc[-2]:
                result.weekly_price_structure = "LOWER_HIGHS_LOWER_LOWS"
            else:
                result.weekly_price_structure = "MIXED"

        ranges = (weekly["high"] - weekly["low"]) / weekly["close"] * 100
        if len(ranges) >= 8:
            baseline = float(ranges.iloc[-8:-4].mean())
            recent = float(ranges.iloc[-4:].mean())
            if baseline > 0:
                result.weekly_contraction_ratio = round(recent / baseline, 4)
                result.weekly_contraction = result.weekly_contraction_ratio <= 0.80

        daily_close = float(frame["close"].iloc[-1])
        daily_sma_50 = pd.to_numeric(frame["close"], errors="coerce").rolling(50).mean().iloc[-1]
        daily_positive = bool(pd.notna(daily_sma_50) and daily_close > daily_sma_50)
        result.daily_weekly_alignment = bool(
            daily_positive
            and result.weekly_trend == "BULLISH"
            and result.weekly_ma_alignment
        )
        pairs = (
            (result.weekly_trend == "BULLISH", "WEEKLY_TREND_BULLISH"),
            (result.weekly_ma_alignment, "WEEKLY_MA_ALIGNMENT"),
            (
                result.weekly_price_structure == "HIGHER_HIGHS_HIGHER_LOWS",
                "WEEKLY_POSITIVE_STRUCTURE",
            ),
            (result.weekly_contraction, "WEEKLY_CONTRACTION"),
            (result.daily_weekly_alignment, "DAILY_WEEKLY_ALIGNMENT"),
        )
        result.weekly_reason_codes = [code for detected, code in pairs if detected]
        return result


weekly_feature_extractor = WeeklyFeatureExtractor()
