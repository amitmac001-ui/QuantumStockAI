from django.urls import path

from .views import (
    CompanyDetailView,
    CompanyListView,
    CompanyStatsView,
)

app_name = "companies"

urlpatterns = [
    path(
        "",
        CompanyListView.as_view(),
        name="company-list",
    ),

    path(
        "stats/",
        CompanyStatsView.as_view(),
        name="company-stats",
    ),

    path(
        "<str:symbol>/",
        CompanyDetailView.as_view(),
        name="company-detail",
    ),
]
