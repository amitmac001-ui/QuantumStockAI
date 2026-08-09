from __future__ import annotations

import pandas as pd

from .base import Indicator


class SuperTrendIndicator(Indicator):
    name = "SuperTrend"

    def __init__(
        self,
        period: int = 10,
        multiplier: float = 3.0,
    ):
        self.period = period
        self.multiplier = multiplier

    def calculate(
        self,
        df: pd.DataFrame,
    ) -> pd.DataFrame:

        df = df.copy()

        high_low = df["high"] - df["low"]
        high_close = (df["high"] - df["close"].shift()).abs()
        low_close = (df["low"] - df["close"].shift()).abs()

        tr = pd.concat(
            [high_low, high_close, low_close],
            axis=1,
        ).max(axis=1)

        atr = tr.rolling(
            window=self.period,
            min_periods=self.period,
        ).mean()

        hl2 = (df["high"] + df["low"]) / 2

        df["supertrend_upper"] = hl2 + (self.multiplier * atr)
        df["supertrend_lower"] = hl2 - (self.multiplier * atr)

        df["supertrend"] = (
            df["close"] > df["supertrend_upper"]
        ).astype(int)

        return df