from apps.scanner.engine.base import BaseStrategy
from apps.scanner.engine.result import ScanResult


class DarvasStrategy(BaseStrategy):

    name = "darvas"
    version = "1.0.0"
    category = "breakout"
    priority = 30

    LOOKBACK = 20

    def scan(self, context):

        candles = context.candles

        if len(candles) < self.LOOKBACK:
            return None

        window = candles[-self.LOOKBACK:]

        upper = max(float(c.high) for c in window)
        lower = min(float(c.low) for c in window)
        price = float(candles[-1].close)

        breakout = price >= upper

        return ScanResult(
            strategy=self.name,
            signal="BUY" if breakout else "WAIT",
            score=90 if breakout else 45,
            confidence=88 if breakout else 50,
            reason="Darvas Box Breakout",
            metadata={
                "price": price,
                "box_high": upper,
                "box_low": lower,
            },
        )
