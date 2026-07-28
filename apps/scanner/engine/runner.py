import logging

from apps.market.repositories.market_repository import MarketRepository

from .registry import StrategyRegistry
from .result import ScanContext

logger = logging.getLogger(__name__)


class ScannerEngine:

    @classmethod
    def run(cls, symbol):

        candles = list(
            MarketRepository.history(symbol)
        )

        if not candles:
            return []

        context = ScanContext(
            symbol=symbol,
            candles=candles,
            quote=None,
        )

        results = []

        for strategy in StrategyRegistry.all():

            try:

                result = strategy.execute(
                    context
                )

                if result is not None:
                    results.append(result)

            except Exception:

                logger.exception(
                    "Scanner strategy failed: %s",
                    strategy.name,
                )

        return results
