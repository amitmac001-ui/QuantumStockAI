from django.urls import path

from .views import (
    MostActiveAPIView,
    ScannerAPIView,
    TopGainersAPIView,
    TopLosersAPIView,
)

app_name = "scanner"

urlpatterns = [

    path(
        "gainers/",
        TopGainersAPIView.as_view(),
        name="gainers",
    ),

    path(
        "losers/",
        TopLosersAPIView.as_view(),
        name="losers",
    ),

    path(
        "most-active/",
        MostActiveAPIView.as_view(),
        name="most_active",
    ),

    path(
        "<str:symbol>/",
        ScannerAPIView.as_view(),
        name="symbol_scan",
    ),

]
