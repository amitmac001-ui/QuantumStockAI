from django.urls import path

from apps.market.api.views import (
    LTPAPIView,
    OHLCAPIView,
    QuoteAPIView,
)

app_name = "market_api"

urlpatterns = [
    path(
        "ltp/",
        LTPAPIView.as_view(),
        name="ltp",
    ),
    path(
        "quote/",
        QuoteAPIView.as_view(),
        name="quote",
    ),
    path(
        "ohlc/",
        OHLCAPIView.as_view(),
        name="ohlc",
    ),
]
