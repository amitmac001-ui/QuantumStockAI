from .base import BaseIndicator
from .utils import closes


class EMAIndicator(BaseIndicator):

    name = "ema"

    def calculate(self, candles, period=20):

        values = closes(candles)

        if len(values) < period:
            return None

        multiplier = 2 / (period + 1)

        ema = values[0]

        for price in values[1:]:

            ema = (
                (price - ema)
                * multiplier
            ) + ema

        return ema
