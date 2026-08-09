from __future__ import annotations

import pandas as pd

from .base import Indicator


class VWAPIndicator(Indicator):
    name = "VWAP"

    def calculate(
        self,
        df: pd.DataFrame,
    ) -> pd.DataFrame:

        df = df.copy()

        typical_price = (
            df["high"]
            + df["low"]
            + df["close"]
        ) / 3

        cumulative_tp_volume = (
            typical_price * df["volume"]
        ).cumsum()

        cumulative_volume = (
            df["volume"]
        ).cumsum()

        df["vwap"] = (
            cumulative_tp_volume
            / cumulative_volume
        )

        return df