from __future__ import annotations

import pandas as pd

from .base import Indicator


class MACDIndicator(Indicator):
    name = "MACD"

    def __init__(
        self,
        fast: int = 12,
        slow: int = 26,
        signal: int = 9,
    ):
        self.fast = fast
        self.slow = slow
        self.signal = signal

    def calculate(
        self,
        df: pd.DataFrame,
    ) -> pd.DataFrame:

        df = df.copy()

        ema_fast = (
            df["close"]
            .ewm(span=self.fast, adjust=False)
            .mean()
        )

        ema_slow = (
            df["close"]
            .ewm(span=self.slow, adjust=False)
            .mean()
        )

        df["macd"] = ema_fast - ema_slow

        df["macd_signal"] = (
            df["macd"]
            .ewm(span=self.signal, adjust=False)
            .mean()
        )

        df["macd_histogram"] = (
            df["macd"] - df["macd_signal"]
        )

        return df