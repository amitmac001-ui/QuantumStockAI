from apps.scanner.engine.base import BaseStrategy
from apps.scanner.engine.result import ScanResult
from apps.scanner.indicators.sma import SMAIndicator


class MinerviniStrategy(BaseStrategy):

    name = "minervini"
    version = "1.0.0"
    category = "trend"
    priority = 20

    def scan(self, context):

        candles = context.candles

        if len(candles) < 200:
            return None

        sma50 = SMAIndicator().calculate(candles, 50)
        sma150 = SMAIndicator().calculate(candles, 150)
        sma200 = SMAIndicator().calculate(candles, 200)

        price = float(candles[-1].close)

        buy = (
            price > sma50
            and sma50 > sma150
            and sma150 > sma200
        )

        return ScanResult(
            strategy=self.name,
            signal="BUY" if buy else "WAIT",
            score=95 if buy else 40,
            confidence=90 if buy else 40,
            reason="Trend Alignment",
            metadata={
                "price": price,
                "sma50": sma50,
                "sma150": sma150,
                "sma200": sma200,
            },
        )
