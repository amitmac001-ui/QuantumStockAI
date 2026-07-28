from django.urls import path

from .views import HealthCheck

urlpatterns = [
    path(
        "health/",
        HealthCheck.as_view(),
        name="health",
    ),
]
