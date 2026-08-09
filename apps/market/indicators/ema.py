from __future__ import annotations

import pandas as pd

from .base import Indicator


class EMAIndicator(Indicator):
    name = "EMA"

    def __init__(self, periods: list[int] | None = None):
        self.periods = periods or [10, 20, 50, 100, 200]

    def calculate(
        self,
        df: pd.DataFrame,
    ) -> pd.DataFrame:

        df = df.copy()

        for period in self.periods:
            df[f"ema_{period}"] = (
                df["close"]
                .ewm(
                    span=period,
                    adjust=False,
                )
                .mean()
            )

        return df
