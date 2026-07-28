from django.urls import path

from .views import (
    MarketQuoteListView,
    MarketQuoteDetailView,
    MarketOHLCListView,
)

urlpatterns = [

    path(
        "quotes/",
        MarketQuoteListView.as_view(),
        name="market_quotes",
    ),

    path(
        "quotes/<uuid:pk>/",
        MarketQuoteDetailView.as_view(),
        name="market_quote_detail",
    ),

    path(
        "ohlc/",
        MarketOHLCListView.as_view(),
        name="market_ohlc",
    ),

]
