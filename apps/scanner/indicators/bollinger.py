from statistics import mean
from statistics import pstdev

from .base import BaseIndicator
from .utils import closes


class BollingerBandsIndicator(BaseIndicator):

    name = "bollinger"

    def calculate(self, candles, period=20):

        values = closes(candles)

        if len(values) < period:
            return None

        values = values[-period:]

        avg = mean(values)

        deviation = pstdev(values)

        upper = avg + (2 * deviation)

        lower = avg - (2 * deviation)

        return {
            "upper": round(upper, 4),
            "middle": round(avg, 4),
            "lower": round(lower, 4),
        }
