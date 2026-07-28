from .base import BaseIndicator


class ATRIndicator(BaseIndicator):

    name = "atr"

    def calculate(self, candles, period=14):

        if len(candles) < period + 1:
            return None

        true_ranges = []

        for i in range(1, len(candles)):

            current = candles[i]
            previous = candles[i - 1]

            high = float(current.high)
            low = float(current.low)
            previous_close = float(previous.close)

            tr = max(
                high - low,
                abs(high - previous_close),
                abs(low - previous_close),
            )

            true_ranges.append(tr)

        return round(
            sum(true_ranges[-period:]) / period,
            4,
        )
