from statistics import mean, pstdev

from apps.scanner.engine.base import BaseStrategy
from apps.scanner.engine.result import ScanResult


class SorosStrategy(BaseStrategy):

    name = "soros"
    version = "1.0.0"
    category = "macro"
    priority = 90

    def scan(self, context):

        candles = context.candles

        if len(candles) < 40:
            return None

        closes = [float(c.close) for c in candles[-40:]]
        returns = [
            (closes[i] - closes[i - 1]) / closes[i - 1]
            for i in range(1, len(closes))
            if closes[i - 1] != 0
        ]

        momentum = mean(returns) if returns else 0
        risk = pstdev(returns) if len(returns) > 1 else 0
        latest = closes[-1]

        buy = momentum > 0 and risk < 0.04

        return ScanResult(
            strategy=self.name,
            signal="BUY" if buy else "WAIT",
            score=86 if buy else 42,
            confidence=80 if buy else 45,
            reason="Momentum Risk Filter",
            metadata={
                "momentum": round(momentum, 6),
                "risk": round(risk, 6),
                "latest": latest,
            },
        )
