from __future__ import annotations

import pandas as pd

from .base import Indicator


class ATRIndicator(Indicator):
    name = "ATR"

    def __init__(self, period: int = 14):
        self.period = period

    def calculate(
        self,
        df: pd.DataFrame,
    ) -> pd.DataFrame:

        df = df.copy()

        high_low = df["high"] - df["low"]

        high_close = (
            df["high"] - df["close"].shift(1)
        ).abs()

        low_close = (
            df["low"] - df["close"].shift(1)
        ).abs()

        true_range = pd.concat(
            [
                high_low,
                high_close,
                low_close,
            ],
            axis=1,
        ).max(axis=1)

        df["atr"] = (
            true_range
            .rolling(
                window=self.period,
                min_periods=self.period,
            )
            .mean()
        )

        return df