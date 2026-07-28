class RankingEngine:

    @staticmethod
    def rank(results):

        return sorted(
            results,
            key=lambda r: (
                r.score,
                r.confidence,
                r.strategy,
            ),
            reverse=True,
        )
