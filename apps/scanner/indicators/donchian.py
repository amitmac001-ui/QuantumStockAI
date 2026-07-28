from .base import BaseIndicator
from .utils import highs
from .utils import lows


class DonchianIndicator(BaseIndicator):

    name = "donchian"

    def calculate(self, candles, period=20):

        if len(candles) < period:
            return None

        window = candles[-period:]

        upper = max(highs(window))

        lower = min(lows(window))

        return {
            "upper": upper,
            "lower": lower,
            "middle": (upper + lower) / 2,
        }
