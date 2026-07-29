from django.db.models import Count
from django.db.models import QuerySet

from apps.core.repositories.base import BaseRepository
from apps.market.models import MarketOHLC
from apps.market.models import MarketQuote


class MarketRepository(BaseRepository):

    model = MarketQuote

    @classmethod
    def all_quotes(cls) -> QuerySet:
        return cls.model.objects.all()

    @classmethod
    def latest_quotes(cls, limit=10) -> QuerySet:
        return (
            cls.model.objects
            .order_by("-updated_at")[:limit]
        )

    @classmethod
    def market_indices(cls) -> QuerySet:
        return (
            cls.model.objects
            .filter(exchange="NSE")
            .filter(
                symbol__in=[
                    "NIFTY 50",
                    "NIFTY BANK",
                    "SENSEX",
                ]
            )
        )

    @classmethod
    def top_gainers(cls, limit=5) -> QuerySet:
        return (
            cls.model.objects
            .order_by("-change_percent")[:limit]
        )

    @classmethod
    def top_losers(cls, limit=5) -> QuerySet:
        return (
            cls.model.objects
            .order_by("change_percent")[:limit]
        )

    @classmethod
    def market_summary(cls) -> dict:
        return {
            "total_quotes": cls.model.objects.count(),
            "nse_quotes": cls.model.objects.filter(exchange="NSE").count(),
            "bse_quotes": cls.model.objects.filter(exchange="BSE").count(),
        }

    @classmethod
    def advance_decline(cls) -> dict:
        return {
            "advances": cls.model.objects.filter(change_percent__gt=0).count(),
            "declines": cls.model.objects.filter(change_percent__lt=0).count(),
            "unchanged": cls.model.objects.filter(change_percent=0).count(),
        }

    @classmethod
    def most_active(cls, limit=10) -> QuerySet:
        return (
            cls.model.objects
            .order_by("-volume")[:limit]
        )

    @classmethod
    def quote(cls, symbol: str):
        return (
            cls.model.objects
            .filter(symbol=symbol.upper())
            .first()
        )

    @classmethod
    def history(cls, symbol: str) -> QuerySet:
        return (
            MarketHistory.objects
            .filter(symbol=symbol.upper())
            .order_by("-date")
        )

    @classmethod
    def latest_candle(cls, symbol: str):
        return (
            MarketHistory.objects
            .filter(symbol=symbol.upper())
            .order_by("-date")
            .first()
        )
