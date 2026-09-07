from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.http import Http404
from django.shortcuts import render

from apps.dashboard.services.dashboard_service import DashboardService
from apps.dashboard.services.stock_detail_service import StockDetailService
from apps.companies.models import Company


@login_required
def dashboard(request):
    return render(
        request,
        "pages/home.html",
        DashboardService.dashboard_context(),
    )


@login_required
def stock_detail(request, symbol):
    try:
        stock = StockDetailService.detail(symbol)
    except Company.DoesNotExist as exc:
        raise Http404("Stock not found") from exc
    return render(
        request,
        "pages/stock_detail.html",
        {
            "stock": stock,
            "market_stale_after": settings.MARKET_DATA_STALE_AFTER_SECONDS,
        },
    )
