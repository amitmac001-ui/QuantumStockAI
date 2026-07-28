from apps.scanner.engine.base import BaseStrategy
from apps.scanner.engine.result import ScanResult


class LivermoreStrategy(BaseStrategy):

    name = "livermore"
    version = "1.0.0"
    category = "pivot"
    priority = 60

    LOOKBACK = 50

    def scan(self, context):

        candles = context.candles

        if len(candles) < self.LOOKBACK:
            return None

        window = candles[-self.LOOKBACK:]

        pivot_high = max(float(c.high) for c in window)
        pivot_low = min(float(c.low) for c in window)

        price = float(candles[-1].close)

        if price >= pivot_high:
            signal = "BUY"
            score = 95
            confidence = 90
        elif price <= pivot_low:
            signal = "SELL"
            score = 5
            confidence = 90
        else:
            signal = "WAIT"
            score = 50
            confidence = 60

        return ScanResult(
            strategy=self.name,
            signal=signal,
            score=score,
            confidence=confidence,
            reason="Livermore Pivot",
            metadata={
                "price": price,
                "pivot_high": pivot_high,
                "pivot_low": pivot_low,
            },
        )
