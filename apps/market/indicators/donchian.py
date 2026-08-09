from __future__ import annotations

import pandas as pd

from .base import Indicator


class DonchianChannelIndicator(Indicator):
    name = "Donchian Channel"

    def __init__(
        self,
        period: int = 20,
    ):
        self.period = period

    def calculate(
        self,
        df: pd.DataFrame,
    ) -> pd.DataFrame:

        df = df.copy()

        df["donchian_upper"] = (
            df["high"]
            .rolling(
                window=self.period,
                min_periods=self.period,
            )
            .max()
        )

        df["donchian_lower"] = (
            df["low"]
            .rolling(
                window=self.period,
                min_periods=self.period,
            )
            .min()
        )

        df["donchian_middle"] = (
            df["donchian_upper"]
            + df["donchian_lower"]
        ) / 2

        df["donchian_breakout"] = (
            df["close"]
            > df["donchian_upper"].shift(1)
        )

        return df