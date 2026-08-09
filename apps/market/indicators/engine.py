from __future__ import annotations

import pandas as pd

from .adx import ADXIndicator
from .atr import ATRIndicator
from .bollinger import BollingerBandsIndicator
from .donchian import DonchianChannelIndicator
from .ema import EMAIndicator
from .macd import MACDIndicator
from .rsi import RSIIndicator
from .supertrend import SuperTrendIndicator
from .vwap import VWAPIndicator


class IndicatorEngine:
    """
    Runs all technical indicators sequentially.
    """

    def __init__(self):
        self.indicators = [
            EMAIndicator(),
            RSIIndicator(),
            MACDIndicator(),
            ATRIndicator(),
            ADXIndicator(),
            SuperTrendIndicator(),
            VWAPIndicator(),
            BollingerBandsIndicator(),
            DonchianChannelIndicator(),
        ]

    def calculate(
        self,
        df: pd.DataFrame,
    ) -> pd.DataFrame:

        result = df.copy()

        for indicator in self.indicators:
            result = indicator(result)

        return result


indicator_engine = IndicatorEngine()