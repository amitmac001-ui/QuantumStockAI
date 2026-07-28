from statistics import mean

from apps.scanner.engine.base import BaseStrategy
from apps.scanner.engine.result import ScanResult


class LynchStrategy(BaseStrategy):

    name = "lynch"
    version = "1.0.0"
    category = "growth"
    priority = 80

    def scan(self, context):

        candles = context.candles

        if len(candles) < 30:
            return None

        closes = [float(c.close) for c in candles[-30:]]
        volumes = [int(c.volume) for c in candles[-30:]]

        latest = closes[-1]
        high_20 = max(closes[-20:])
        avg_volume = mean(volumes)

        breakout = latest >= high_20 and volumes[-1] > avg_volume * 1.25

        return ScanResult(
            strategy=self.name,
            signal="BUY" if breakout else "WAIT",
            score=88 if breakout else 44,
            confidence=82 if breakout else 48,
            reason="Growth Breakout Filter",
            metadata={
                "latest": latest,
                "high_20": high_20,
                "avg_volume": round(avg_volume, 2),
                "volume": volumes[-1],
            },
        )
