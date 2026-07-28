from django.db.models import QuerySet

from apps.core.repositories.base import BaseRepository
from apps.market.models import MarketOHLC
from apps.market.models import MarketQuote


class MarketRepository(BaseRepository):

    model = MarketQuote

    @classmethod
    def quote(cls, symbol: str):

        return (
            cls.model.objects
            .filter(symbol=symbol)
            .first()
        )

    @classmethod
    def quotes(
        cls,
        symbols: list[str],
    ) -> QuerySet:

        return (
            cls.model.objects
            .filter(symbol__in=symbols)
        )

    @classmethod
    def all_quotes(cls) -> QuerySet:

        return cls.model.objects.all()

    @classmethod
    def history(
        cls,
        symbol: str,
        interval: str = "1d",
    ) -> QuerySet:

        return (
            MarketOHLC.objects
            .filter(
                symbol=symbol,
                interval=interval,
            )
            .order_by("candle_time")
        )

    @classmethod
    def latest_candle(
        cls,
        symbol: str,
        interval: str = "1d",
    ):

        return (
            MarketOHLC.objects
            .filter(
                symbol=symbol,
                interval=interval,
            )
            .order_by("-candle_time")
            .first()
        )
