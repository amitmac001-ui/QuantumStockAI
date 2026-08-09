from __future__ import annotations

from dataclasses import asdict, dataclass, field
from math import isfinite
from typing import Any, Iterable, MutableMapping

import pandas as pd

from .prebreakout_config import (
    RS_BENCHMARK_EXCHANGE,
    RS_BENCHMARK_SYMBOL,
    RS_COMPOSITE_WEIGHTS,
    RS_DETERIORATING_MAX_SLOPE_PER_DAY,
    RS_HORIZON_OBSERVATIONS,
    RS_IMPROVING_MIN_SLOPE_PER_DAY,
    RS_NEW_HIGH_LOOKBACK,
    RS_NEW_HIGH_TOLERANCE_PERCENT,
    RS_SLOPE_LOOKBACK,
)


@dataclass(slots=True)
class RelativeStrengthFeatures:
    rs_1m_pct: float | None = None
    rs_3m_pct: float | None = None
    rs_6m_pct: float | None = None
    rs_12m_pct: float | None = None
    rs_slope_pct_per_day: float | None = None
    rs_acceleration: float | None = None
    rs_trend_status: str | None = None
    rs_improving: bool | None = None
    rs_deteriorating: bool | None = None
    rs_new_high: bool | None = None
    rs_line_near_high: bool | None = None
    rs_line_distance_from_high_pct: float | None = None
    rs_line_leading_price: bool | None = None
    sector_rs_status: str = "DATA_UNAVAILABLE"
    rs_composite_score: float | None = None
    rs_rating: int | None = None
    rs_reason_codes: list[str] = field(default_factory=list)
    data_quality: list[str] = field(default_factory=list)

    def as_mapping(self) -> dict[str, Any]:
        return asdict(self)


class RelativeStrengthFeatureExtractor:
    """Stock-vs-NIFTY price RS. This module never reads or calculates RSI."""

    REQUIRED_COLUMNS = frozenset({"timestamp", "close"})

    @staticmethod
    def _prepared(frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty or not RelativeStrengthFeatureExtractor.REQUIRED_COLUMNS.issubset(
            frame.columns
        ):
            return pd.DataFrame(columns=["timestamp", "close"])
        prepared = frame.loc[:, ["timestamp", "close"]].copy()
        prepared["timestamp"] = pd.to_datetime(
            prepared["timestamp"], errors="coerce", utc=True
        )
        # Historical providers may represent the same NSE session at midnight
        # or intraday time. Align by the Asia/Kolkata trading date, not raw time.
        prepared["timestamp"] = (
            prepared["timestamp"].dt.tz_convert("Asia/Kolkata").dt.normalize()
        )
        prepared["close"] = pd.to_numeric(prepared["close"], errors="coerce")
        prepared = prepared.dropna().loc[lambda item: item["close"] > 0]
        return (
            prepared.sort_values("timestamp")
            .drop_duplicates("timestamp", keep="last")
            .reset_index(drop=True)
        )

    @staticmethod
    def _relative_return(window: pd.DataFrame) -> float | None:
        stock_start = float(window["stock_close"].iloc[0])
        stock_end = float(window["stock_close"].iloc[-1])
        benchmark_start = float(window["benchmark_close"].iloc[0])
        benchmark_end = float(window["benchmark_close"].iloc[-1])
        if min(stock_start, stock_end, benchmark_start, benchmark_end) <= 0:
            return None
        value = ((stock_end / stock_start) / (benchmark_end / benchmark_start) - 1) * 100
        return round(value, 4) if isfinite(value) else None

    @staticmethod
    def _linear_slope(values: pd.Series) -> float | None:
        numeric = pd.to_numeric(values, errors="coerce").dropna().reset_index(drop=True)
        count = len(numeric)
        if count < 2:
            return None
        x_mean = (count - 1) / 2
        y_mean = float(numeric.mean())
        denominator = sum((index - x_mean) ** 2 for index in range(count))
        if denominator <= 0:
            return None
        numerator = sum(
            (index - x_mean) * (float(value) - y_mean)
            for index, value in enumerate(numeric)
        )
        slope = numerator / denominator
        return round(slope, 6) if isfinite(slope) else None

    @classmethod
    def extract(
        cls,
        stock_frame: pd.DataFrame,
        benchmark_frame: pd.DataFrame,
    ) -> RelativeStrengthFeatures:
        result = RelativeStrengthFeatures()
        stock = cls._prepared(stock_frame)
        benchmark = cls._prepared(benchmark_frame)

        if stock.empty:
            result.data_quality.append("RS_STOCK_HISTORY_UNAVAILABLE")
        if benchmark.empty:
            result.data_quality.append("BENCHMARK_HISTORY_UNAVAILABLE")
        if stock.empty or benchmark.empty:
            return result

        longest_horizon = max(RS_HORIZON_OBSERVATIONS.values())
        if len(stock) < longest_horizon:
            result.data_quality.append("INSUFFICIENT_RS_HISTORY")
        if len(benchmark) < longest_horizon:
            result.data_quality.append("INSUFFICIENT_BENCHMARK_HISTORY")

        aligned = stock.merge(
            benchmark,
            on="timestamp",
            how="inner",
            suffixes=("_stock", "_benchmark"),
        ).rename(
            columns={
                "close_stock": "stock_close",
                "close_benchmark": "benchmark_close",
            }
        )
        if aligned.empty:
            result.data_quality.append("RS_ALIGNED_HISTORY_UNAVAILABLE")
            return result
        if len(aligned) < longest_horizon:
            result.data_quality.append("INSUFFICIENT_ALIGNED_RS_HISTORY")

        horizon_values: dict[str, float] = {}
        for label, observations in RS_HORIZON_OBSERVATIONS.items():
            if len(aligned) < observations:
                continue
            value = cls._relative_return(aligned.tail(observations))
            if value is not None:
                horizon_values[label] = value
                setattr(result, f"rs_{label}_pct", value)

        rs_line = aligned["stock_close"] / aligned["benchmark_close"] * 100
        if len(rs_line) >= RS_SLOPE_LOOKBACK:
            result.rs_slope_pct_per_day = cls._linear_slope(
                rs_line.tail(RS_SLOPE_LOOKBACK)
            )
            if result.rs_slope_pct_per_day is not None:
                if result.rs_slope_pct_per_day >= RS_IMPROVING_MIN_SLOPE_PER_DAY:
                    result.rs_trend_status = "IMPROVING"
                    result.rs_improving = True
                    result.rs_deteriorating = False
                elif (
                    result.rs_slope_pct_per_day
                    <= RS_DETERIORATING_MAX_SLOPE_PER_DAY
                ):
                    result.rs_trend_status = "DETERIORATING"
                    result.rs_improving = False
                    result.rs_deteriorating = True
                else:
                    result.rs_trend_status = "STABLE"
                    result.rs_improving = False
                    result.rs_deteriorating = False

        acceleration_window = max(RS_SLOPE_LOOKBACK, 20)
        if len(rs_line) >= acceleration_window * 2:
            prior_slope = cls._linear_slope(
                rs_line.iloc[-acceleration_window * 2:-acceleration_window]
            )
            recent_slope = cls._linear_slope(rs_line.tail(acceleration_window))
            if prior_slope is not None and recent_slope is not None:
                result.rs_acceleration = round(recent_slope - prior_slope, 6)

        if len(rs_line) >= RS_NEW_HIGH_LOOKBACK:
            recent = rs_line.tail(RS_NEW_HIGH_LOOKBACK)
            previous_high = float(recent.iloc[:-1].max())
            latest = float(recent.iloc[-1])
            tolerance = previous_high * RS_NEW_HIGH_TOLERANCE_PERCENT / 100
            result.rs_new_high = bool(latest >= previous_high)
            result.rs_line_near_high = bool(latest >= previous_high - tolerance)
            result.rs_line_distance_from_high_pct = round(
                max(previous_high - latest, 0) / previous_high * 100, 4
            )
            price_window = aligned["stock_close"].tail(RS_NEW_HIGH_LOOKBACK)
            if len(price_window) >= 2:
                prior_price_high = float(price_window.iloc[:-1].max())
                latest_price = float(price_window.iloc[-1])
                result.rs_line_leading_price = bool(
                    result.rs_line_near_high
                    and latest_price < prior_price_high * 0.995
                )

        if len(horizon_values) == len(RS_HORIZON_OBSERVATIONS):
            result.rs_composite_score = round(
                sum(
                    horizon_values[label] * RS_COMPOSITE_WEIGHTS[label]
                    for label in RS_HORIZON_OBSERVATIONS
                ),
                4,
            )

        reason_pairs = (
            (result.rs_improving, "RS_IMPROVING"),
            (result.rs_deteriorating, "RS_DETERIORATING"),
            (result.rs_new_high, "RS_NEW_HIGH"),
            (result.rs_line_near_high, "RS_LINE_NEAR_HIGH"),
            (result.rs_line_leading_price, "RS_LINE_LEADING_PRICE"),
            (
                result.rs_acceleration is not None and result.rs_acceleration > 0,
                "RS_ACCELERATING",
            ),
        )
        result.rs_reason_codes = [
            code for detected, code in reason_pairs if detected is True
        ]
        if horizon_values and all(value > 0 for value in horizon_values.values()):
            result.rs_reason_codes.append("PERSISTENT_MARKET_OUTPERFORMANCE")
        result.data_quality = list(dict.fromkeys(result.data_quality))
        return result


def assign_rs_ratings(snapshots: Iterable[MutableMapping[str, Any]]) -> None:
    """Assign 1–100 midrank percentiles; exact ties always receive one rating."""

    eligible = [
        snapshot
        for snapshot in snapshots
        if snapshot.get("rs_composite_score") is not None
        and not (
            str(snapshot.get("symbol", "")).strip().upper() == RS_BENCHMARK_SYMBOL
            and str(snapshot.get("exchange", "NSE")).strip().upper()
            == RS_BENCHMARK_EXCHANGE
        )
    ]
    if not eligible:
        return

    ordered = sorted(eligible, key=lambda item: float(item["rs_composite_score"]))
    total = len(ordered)
    position = 0
    while position < total:
        end = position + 1
        score = float(ordered[position]["rs_composite_score"])
        while end < total and float(ordered[end]["rs_composite_score"]) == score:
            end += 1
        average_rank = ((position + 1) + end) / 2
        rating = 100 if total == 1 else round(1 + (average_rank - 1) * 99 / (total - 1))
        for snapshot in ordered[position:end]:
            snapshot["rs_rating"] = max(1, min(100, int(rating)))
            if snapshot["rs_rating"] >= 80:
                reasons = snapshot.setdefault("rs_reason_codes", [])
                if "HIGH_RS_RATING" not in reasons:
                    reasons.append("HIGH_RS_RATING")
        position = end


relative_strength_feature_extractor = RelativeStrengthFeatureExtractor()
