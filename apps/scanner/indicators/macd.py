from .base import BaseIndicator
from .ema import EMAIndicator
from .utils import closes


class MACDIndicator(BaseIndicator):

    name = "macd"

    def calculate(
        self,
        candles,
        fast=12,
        slow=26,
    ):

        prices = closes(candles)

        if len(prices) < slow:
            return None

        ema = EMAIndicator()

        fast_value = ema.calculate(candles, fast)

        slow_value = ema.calculate(candles, slow)

        if fast_value is None or slow_value is None:
            return None

        macd = fast_value - slow_value

        return {
            "macd": round(macd, 4),
            "signal": "BUY" if macd > 0 else "SELL",
        }
