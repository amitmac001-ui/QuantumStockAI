from __future__ import annotations

import pandas as pd

from .base import Indicator


class BollingerBandsIndicator(Indicator):
    name = "Bollinger Bands"

    def __init__(
        self,
        period: int = 20,
        std_dev: float = 2.0,
    ):
        self.period = period
        self.std_dev = std_dev

    def calculate(
        self,
        df: pd.DataFrame,
    ) -> pd.DataFrame:

        df = df.copy()

        middle = (
            df["close"]
            .rolling(self.period)
            .mean()
        )

        std = (
            df["close"]
            .rolling(self.period)
            .std()
        )

        df["bb_middle"] = middle
        df["bb_upper"] = middle + (std * self.std_dev)
        df["bb_lower"] = middle - (std * self.std_dev)
        df["bb_width"] = (
            df["bb_upper"] - df["bb_lower"]
        )

        return df