from django.urls import path

from apps.dashboard.views import dashboard

app_name = "dashboard"

urlpatterns = [
    path(
        "",
        dashboard,
        name="home",
    ),
]
