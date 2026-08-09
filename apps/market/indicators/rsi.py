from __future__ import annotations

import pandas as pd

from .base import Indicator


class RSIIndicator(Indicator):
    name = "RSI"

    def __init__(self, period: int = 14):
        self.period = period

    def calculate(
        self,
        df: pd.DataFrame,
    ) -> pd.DataFrame:

        df = df.copy()

        delta = df["close"].diff()

        gain = delta.clip(lower=0)

        loss = -delta.clip(upper=0)

        avg_gain = gain.rolling(
            self.period,
            min_periods=self.period,
        ).mean()

        avg_loss = loss.rolling(
            self.period,
            min_periods=self.period,
        ).mean()

        rs = avg_gain / avg_loss.replace(0, float("nan"))

        df["rsi"] = 100 - (100 / (1 + rs))

        return df