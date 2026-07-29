import logging

from django.shortcuts import render

from apps.market.services.market_data_service import MarketDataService

logger = logging.getLogger(__name__)


def dashboard(request):
    service = MarketDataService(
        request.user if request.user.is_authenticated else None
    )

    indices = [
        "NSE_INDEX|Nifty 50",
        "NSE_INDEX|Nifty Bank",
        "NSE_INDEX|Nifty Financial Services",
    ]

    market = None

    try:
        market = service.quote(indices)
    except Exception as exc:
        logger.exception(exc)
        market = {
            "status": "error",
            "message": "Data Unavailable",
        }

    return render(
        request,
        "dashboard/index.html",
        {
            "market": market,
        },
    )
