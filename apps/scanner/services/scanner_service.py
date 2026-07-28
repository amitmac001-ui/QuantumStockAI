from apps.scanner.engine.ranking import RankingEngine
from apps.scanner.engine.runner import ScannerEngine
from apps.scanner.engine.score import ScoreEngine
from apps.scanner.repositories.scanner_repository import (
    ScannerRepository,
)


class ScannerService:

    DEFAULT_LIMIT = 100

    @classmethod
    def analyze(cls, symbol):

        results = ScannerEngine.run(symbol)

        results = RankingEngine.rank(results)

        summary = ScoreEngine.calculate(results)

        return {
            "symbol": symbol,
            "summary": summary,
            "strategies": results,
        }

    @classmethod
    def top_gainers(cls, limit=None):

        return ScannerRepository.top_gainers()[
            : limit or cls.DEFAULT_LIMIT
        ]

    @classmethod
    def top_losers(cls, limit=None):

        return ScannerRepository.top_losers()[
            : limit or cls.DEFAULT_LIMIT
        ]

    @classmethod
    def most_active(cls, limit=None):

        return ScannerRepository.most_active()[
            : limit or cls.DEFAULT_LIMIT
        ]
