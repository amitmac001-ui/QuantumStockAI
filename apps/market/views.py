from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from .models import (
    MarketQuote,
    MarketOHLC,
)

from .serializers import (
    MarketQuoteSerializer,
    MarketOHLCSerializer,
)


class MarketQuoteListView(generics.ListAPIView):

    serializer_class = MarketQuoteSerializer

    permission_classes = [IsAuthenticated]

    queryset = (
        MarketQuote.objects
        .all()
        .order_by("symbol")
    )


class MarketQuoteDetailView(generics.RetrieveAPIView):

    serializer_class = MarketQuoteSerializer

    permission_classes = [IsAuthenticated]

    queryset = (
        MarketQuote.objects
        .all()
    )


class MarketOHLCListView(generics.ListAPIView):

    serializer_class = MarketOHLCSerializer

    permission_classes = [IsAuthenticated]

    queryset = (
        MarketOHLC.objects
        .all()
        .order_by("-candle_time")
    )
