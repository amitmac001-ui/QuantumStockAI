from apps.companies.services.company_service import CompanyService
from apps.market.services.market_service import MarketService


class DashboardService:

    @staticmethod
    def dashboard_context():

        quotes = MarketService.latest_quotes()
        indices = list(MarketService.market_indices())

        nifty = next(
            (item for item in indices if item.symbol == "NIFTY 50"),
            None,
        )

        sensex = next(
            (item for item in indices if item.symbol == "SENSEX"),
            None,
        )

        return {
            "nifty": nifty,
            "sensex": sensex,
            "total_companies": CompanyService.total_companies(),
            "total_quotes": MarketService.market_summary()["total_quotes"],
            "market_quotes": quotes,
            "market_indices": indices,
            "top_gainers": MarketService.top_gainers(),
            "top_losers": MarketService.top_losers(),
            "market_summary": MarketService.market_summary(),
            "advance_decline": MarketService.advance_decline(),
            "most_active": MarketService.most_active(),
            "last_updated": (
                quotes.first().updated_at
                if quotes.exists()
                else None
            ),
        }
