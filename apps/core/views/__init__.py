from django.shortcuts import render

from apps.dashboard.services.dashboard_service import DashboardService


def home(request):
    return render(
        request,
        "pages/home.html",
        DashboardService.dashboard_context(),
    )
