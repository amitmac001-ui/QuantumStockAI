from django.urls import path

from apps.dashboard.api.views import DashboardAPIView

app_name = "dashboard_api"

urlpatterns = [
    path(
        "",
        DashboardAPIView.as_view(),
        name="dashboard",
    ),
]
