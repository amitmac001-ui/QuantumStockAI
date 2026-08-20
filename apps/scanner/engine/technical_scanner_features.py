from __future__ import annotations

from math import isfinite
from typing import Any

import pandas as pd

from apps.market.indicators.rsi import RSIIndicator


class TechnicalScannerFeatureExtractor:
    """Presentation-only technical values from committed daily bars."""

    MA_PERIODS = (20, 50, 100, 200)
    RSI_PERIODS = (5, 9, 14, 21)

    @staticmethod
    def _number(value: Any) -> float | None:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return round(number, 4) if isfinite(number) else None

    @classmethod
    def _value(cls, frame: pd.DataFrame, column: str, offset: int = -1):
        if column not in frame or len(frame) < abs(offset):
            return None
        return cls._number(frame[column].iloc[offset])

    @staticmethod
    def _cross(previous_price, previous_average, price, average):
        if None in (previous_price, previous_average, price, average):
            return None
        return bool(previous_price <= previous_average and price > average)

    @classmethod
    def extract(cls, frame: pd.DataFrame) -> dict[str, Any]:
        if frame.empty or "close" not in frame:
            return {"technical_data_available": False}

        work = frame.copy()
        work["close"] = pd.to_numeric(work["close"], errors="coerce")
        output: dict[str, Any] = {"technical_data_available": True}
        current_close = cls._value(work, "close")
        previous_close = cls._value(work, "close", -2)

        for period in cls.MA_PERIODS:
            sma_column = f"sma_{period}"
            if sma_column not in work:
                work[sma_column] = work["close"].rolling(
                    period, min_periods=period
                ).mean()
            ema_column = f"ema_{period}"
            output[sma_column] = cls._value(work, sma_column)
            output[f"price_vs_{sma_column}"] = cls._position(
                current_close, output[sma_column]
            )
            output[f"{sma_column}_bullish_cross"] = cls._cross(
                previous_close, cls._value(work, sma_column, -2),
                current_close, output[sma_column],
            )
            output[ema_column] = cls._value(work, ema_column)
            output[f"price_vs_{ema_column}"] = cls._position(
                current_close, output[ema_column]
            )
            output[f"{ema_column}_bullish_cross"] = cls._cross(
                previous_close, cls._value(work, ema_column, -2),
                current_close, output[ema_column],
            )

        for period in cls.RSI_PERIODS:
            calculated = RSIIndicator(period=period).calculate(work[["close"]])
            output[f"rsi_{period}"] = cls._value(calculated, "rsi")

        macd = cls._value(work, "macd")
        signal = cls._value(work, "macd_signal")
        previous_macd = cls._value(work, "macd", -2)
        previous_signal = cls._value(work, "macd_signal", -2)
        output.update(
            macd=macd,
            macd_signal=signal,
            macd_histogram=cls._value(work, "macd_histogram"),
            macd_bullish_cross=(
                None if None in (previous_macd, previous_signal, macd, signal)
                else previous_macd <= previous_signal and macd > signal
            ),
            macd_bearish_cross=(
                None if None in (previous_macd, previous_signal, macd, signal)
                else previous_macd >= previous_signal and macd < signal
            ),
        )

        middle = cls._value(work, "bb_middle")
        upper = cls._value(work, "bb_upper")
        lower = cls._value(work, "bb_lower")
        output.update(
            bb_upper=upper,
            bb_middle=middle,
            bb_lower=lower,
            bb_width_pct=(
                None if None in (upper, lower, middle) or middle <= 0
                else round((upper - lower) / middle * 100, 4)
            ),
            price_position_in_bb=cls._bb_position(current_close, lower, upper),
        )
        atr = cls._value(work, "atr")
        prior_atr = cls._value(work, "atr", -2)
        output.update(
            atr_14=atr,
            atr_pct=(
                None if atr is None or current_close is None or current_close <= 0
                else round(atr / current_close * 100, 4)
            ),
            atr_contracting=(
                None if atr is None or prior_atr is None else atr < prior_atr
            ),
            atr_expansion=(
                None if atr is None or prior_atr is None else atr > prior_atr
            ),
            adx_14=cls._value(work, "adx"),
            plus_di=cls._value(work, "plus_di"),
            minus_di=cls._value(work, "minus_di"),
            last_committed_bar_close=current_close,
            last_committed_bar_timestamp=(
                None if "timestamp" not in work else work["timestamp"].iloc[-1]
            ),
        )
        return output

    @staticmethod
    def _position(price, average):
        if price is None or average is None:
            return "DATA_UNAVAILABLE"
        return "ABOVE" if price > average else "BELOW" if price < average else "AT"

    @staticmethod
    def _bb_position(price, lower, upper):
        if None in (price, lower, upper) or upper <= lower:
            return "DATA_UNAVAILABLE"
        if price > upper:
            return "ABOVE_UPPER"
        if price < lower:
            return "BELOW_LOWER"
        return round((price - lower) / (upper - lower) * 100, 2)

    @staticmethod
    def committed_vwap_transition(
        previous_close, current_close, previous_vwap, current_vwap
    ) -> tuple[bool | None, bool | None]:
        if None in (previous_close, current_close, previous_vwap, current_vwap):
            return None, None
        reclaim = previous_close <= previous_vwap and current_close > current_vwap
        breakdown = previous_close >= previous_vwap and current_close < current_vwap
        return bool(reclaim), bool(breakdown)


technical_scanner_feature_extractor = TechnicalScannerFeatureExtractor()
