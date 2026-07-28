from apps.scanner.engine.base import BaseStrategy
from apps.scanner.engine.result import ScanResult
from apps.scanner.indicators.donchian import DonchianIndicator


class DonchianStrategy(BaseStrategy):

    name = "donchian"
    version = "1.0.0"
    category = "breakout"
    priority = 10

    def scan(self, context):

        candles = context.candles

        channel = DonchianIndicator().calculate(candles)

        if not channel:
            return None

        upper = float(channel["upper"])
        lower = float(channel["lower"])
        middle = float(channel["middle"])

        price = float(candles[-1].close)

        if price >= upper:
            signal = "BUY"
            score = 100
            confidence = 95
        elif price <= lower:
            signal = "SELL"
            score = 0
            confidence = 95
        else:
            signal = "WAIT"
            score = 50
            confidence = 60

        return ScanResult(
            strategy=self.name,
            signal=signal,
            score=score,
            confidence=confidence,
            reason="Donchian Breakout",
            metadata={
                "price": price,
                "upper": upper,
                "middle": middle,
                "lower": lower,
            },
        )
