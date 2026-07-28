from statistics import mean

from apps.scanner.engine.base import BaseStrategy
from apps.scanner.engine.result import ScanResult


class BuffettStrategy(BaseStrategy):

    name = "buffett"
    version = "1.0.0"
    category = "quality"
    priority = 70

    def scan(self, context):

        candles = context.candles

        if len(candles) < 60:
            return None

        closes = [float(c.close) for c in candles[-60:]]
        returns = [
            (closes[i] - closes[i - 1]) / closes[i - 1]
            for i in range(1, len(closes))
            if closes[i - 1] != 0
        ]

        avg_price = mean(closes)
        avg_return = mean(returns) if returns else 0
        volatility = mean([abs(r) for r in returns]) if returns else 0
        latest = closes[-1]

        buy = (
            latest > avg_price
            and avg_return > 0
            and volatility < 0.03
        )

        return ScanResult(
            strategy=self.name,
            signal="BUY" if buy else "WAIT",
            score=90 if buy else 45,
            confidence=85 if buy else 50,
            reason="Quality Trend Filter",
            metadata={
                "latest": latest,
                "avg_price": round(avg_price, 4),
                "avg_return": round(avg_return, 6),
                "volatility": round(volatility, 6),
            },
        )
