from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.market.services.market_data_service import (
    MarketDataService,
)


class LTPAPIView(APIView):

    def get(self, request):
        symbols = request.GET.get("symbols")

        if not symbols:
            return Response(
                {
                    "status": "error",
                    "message": "symbols parameter required",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        service = MarketDataService(request.user)

        data = service.ltp(symbols)

        return Response(data)


class QuoteAPIView(APIView):

    def get(self, request):
        symbols = request.GET.get("symbols")

        if not symbols:
            return Response(
                {
                    "status": "error",
                    "message": "symbols parameter required",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        service = MarketDataService(request.user)

        data = service.quote(symbols)

        return Response(data)


class OHLCAPIView(APIView):

    def get(self, request):
        symbols = request.GET.get("symbols")
        interval = request.GET.get("interval", "1d")

        if not symbols:
            return Response(
                {
                    "status": "error",
                    "message": "symbols parameter required",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        service = MarketDataService(request.user)

        data = service.ohlc(
            symbols=symbols,
            interval=interval,
        )

        return Response(data)
