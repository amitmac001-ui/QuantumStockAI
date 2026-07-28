from statistics import mean

from .base import BaseIndicator
from .utils import closes


class SMAIndicator(BaseIndicator):

    name = "sma"

    def calculate(self, candles, period=20):

        values = closes(candles)

        if len(values) < period:
            return None

        return mean(values[-period:])
