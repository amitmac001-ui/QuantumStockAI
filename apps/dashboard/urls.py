from django.urls import path

from apps.dashboard.views import dashboard, stock_detail

app_name = "dashboard"

urlpatterns = [
    path(
        "",
        dashboard,
        name="home",
    ),
    path(
        "stock/<str:symbol>/",
        stock_detail,
        name="stock-detail",
    ),
]
