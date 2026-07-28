from apps.scanner.engine.base import BaseStrategy
from apps.scanner.engine.result import ScanResult
from apps.scanner.indicators.sma import SMAIndicator


class CANSLIMStrategy(BaseStrategy):

    name = "canslim"
    version = "1.0.0"
    category = "growth"
    priority = 40

    def scan(self, context):

        candles = context.candles

        if len(candles) < 200:
            return None

        sma50 = SMAIndicator().calculate(candles, 50)
        sma200 = SMAIndicator().calculate(candles, 200)

        price = float(candles[-1].close)

        volume = int(candles[-1].volume)

        avg_volume = (
            sum(
                c.volume
                for c in candles[-50:]
            ) / 50
        )

        buy = (
            price > sma50
            and price > sma200
            and volume > avg_volume
        )

        return ScanResult(
            strategy=self.name,
            signal="BUY" if buy else "WAIT",
            score=92 if buy else 45,
            confidence=90 if buy else 50,
            reason="Growth Trend",
            metadata={
                "price": price,
                "volume": volume,
                "average_volume": round(avg_volume),
                "sma50": sma50,
                "sma200": sma200,
            },
        )
