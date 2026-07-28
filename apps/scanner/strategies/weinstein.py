from apps.scanner.engine.base import BaseStrategy
from apps.scanner.engine.result import ScanResult
from apps.scanner.indicators.sma import SMAIndicator


class WeinsteinStrategy(BaseStrategy):

    name = "weinstein"
    version = "1.0.0"
    category = "stage"
    priority = 50

    def scan(self, context):

        candles = context.candles

        if len(candles) < 200:
            return None

        sma30 = SMAIndicator().calculate(candles, 30)
        sma150 = SMAIndicator().calculate(candles, 150)

        price = float(candles[-1].close)

        stage = 1

        if price > sma30 > sma150:
            stage = 2
        elif price < sma30 and sma30 > sma150:
            stage = 3
        elif price < sma30 < sma150:
            stage = 4

        signal = "BUY" if stage == 2 else "WAIT"

        return ScanResult(
            strategy=self.name,
            signal=signal,
            score=95 if signal == "BUY" else 45,
            confidence=90 if signal == "BUY" else 50,
            reason=f"Stage {stage}",
            metadata={
                "stage": stage,
                "price": price,
                "sma30": sma30,
                "sma150": sma150,
            },
        )
