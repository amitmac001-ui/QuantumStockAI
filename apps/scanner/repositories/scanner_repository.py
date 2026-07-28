from apps.market.models import MarketQuote


class ScannerRepository:

    @staticmethod
    def all_quotes():

        return (
            MarketQuote.objects
            .all()
        )

    @classmethod
    def queryset(cls):

        return (
            cls.all_quotes()
            .only(
                "symbol",
                "exchange",
                "company_name",
                "last_price",
                "change",
                "change_percent",
                "volume",
                "market_status",
                "updated_at",
            )
        )

    @classmethod
    def top_gainers(cls):

        return (
            cls.queryset()
            .order_by(
                "-change_percent",
                "-volume",
            )
        )

    @classmethod
    def top_losers(cls):

        return (
            cls.queryset()
            .order_by(
                "change_percent",
                "-volume",
            )
        )

    @classmethod
    def most_active(cls):

        return (
            cls.queryset()
            .order_by("-volume")
        )
