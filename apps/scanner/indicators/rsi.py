from .base import BaseIndicator
from .utils import closes


class RSIIndicator(BaseIndicator):

    name = "rsi"

    def calculate(self, candles, period=14):

        prices = closes(candles)

        if len(prices) < period + 1:
            return None

        gains = []
        losses = []

        for i in range(1, period + 1):

            change = prices[-period - 1 + i] - prices[-period - 2 + i]

            if change >= 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))

        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period

        if avg_loss == 0:
            return 100

        rs = avg_gain / avg_loss

        return round(
            100 - (100 / (1 + rs)),
            2,
        )
