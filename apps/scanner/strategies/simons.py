from statistics import mean

from apps.scanner.engine.base import BaseStrategy
from apps.scanner.engine.result import ScanResult


class SimonsStrategy(BaseStrategy):

    name = "simons"
    version = "1.0.0"
    category = "quant"
    priority = 100

    def scan(self, context):

        candles = context.candles

        if len(candles) < 25:
            return None

        closes = [float(c.close) for c in candles[-25:]]
        recent = closes[-1]
        avg_5 = mean(closes[-5:])
        avg_10 = mean(closes[-10:])
        avg_20 = mean(closes[-20:])

        score = 0

        if recent > avg_5:
            score += 30
        if avg_5 > avg_10:
            score += 25
        if avg_10 > avg_20:
            score += 25
        if recent > closes[0]:
            score += 20

        return ScanResult(
            strategy=self.name,
            signal="BUY" if score >= 70 else "WAIT",
            score=score,
            confidence=score,
            reason="Quant Momentum Stack",
            metadata={
                "recent": recent,
                "avg_5": round(avg_5, 4),
                "avg_10": round(avg_10, 4),
                "avg_20": round(avg_20, 4),
            },
        )
