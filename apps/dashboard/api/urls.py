from django.urls import path

from apps.dashboard.api.views import (
    DashboardHomeAPIView,
    DashboardSearchAPIView,
    DashboardStockDetailAPIView,
)

app_name = "dashboard_api"

urlpatterns = [
    path(
        "",
        DashboardHomeAPIView.as_view(),
        name="dashboard",
    ),
    path(
        "home/",
        DashboardHomeAPIView.as_view(),
        name="home",
    ),
    path(
        "search/",
        DashboardSearchAPIView.as_view(),
        name="search",
    ),
    path(
        "stocks/<str:symbol>/",
        DashboardStockDetailAPIView.as_view(),
        name="stock-detail",
    ),
]
