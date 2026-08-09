from __future__ import annotations

import pandas as pd

from .base import Indicator


class ADXIndicator(Indicator):
    name = "ADX"

    def __init__(self, period: int = 14):
        self.period = period

    def calculate(
        self,
        df: pd.DataFrame,
    ) -> pd.DataFrame:

        df = df.copy()

        up_move = df["high"].diff()
        down_move = -df["low"].diff()

        plus_dm = up_move.where(
            (up_move > down_move) & (up_move > 0),
            0.0,
        )

        minus_dm = down_move.where(
            (down_move > up_move) & (down_move > 0),
            0.0,
        )

        high_low = df["high"] - df["low"]
        high_close = (df["high"] - df["close"].shift()).abs()
        low_close = (df["low"] - df["close"].shift()).abs()

        tr = pd.concat(
            [high_low, high_close, low_close],
            axis=1,
        ).max(axis=1)

        atr = tr.rolling(
            self.period,
            min_periods=self.period,
        ).mean()

        plus_di = (
            100
            * plus_dm.rolling(self.period).mean()
            / atr
        )

        minus_di = (
            100
            * minus_dm.rolling(self.period).mean()
            / atr
        )

        dx = (
            (plus_di - minus_di).abs()
            / (plus_di + minus_di)
        ) * 100

        df["plus_di"] = plus_di
        df["minus_di"] = minus_di
        df["adx"] = dx.rolling(
            self.period,
            min_periods=self.period,
        ).mean()

        return df