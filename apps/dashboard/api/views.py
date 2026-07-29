from rest_framework.response import Response
from rest_framework.views import APIView

from apps.market.services.market_data_service import (
    MarketDataService,
)


class DashboardAPIView(APIView):

    def get(self, request):
        service = MarketDataService(request.user)

        indices = [
            "NSE_INDEX|Nifty 50",
            "NSE_INDEX|Nifty Bank",
            "NSE_INDEX|Nifty Financial Services",
        ]

        return Response(
            {
                "market": service.quote(indices),
                "status": "success",
            }
        )
