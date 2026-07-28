from django.shortcuts import render

from apps.companies.models import Company
from apps.market.models import MarketQuote


def home(request):
    return render(
        request,
        "pages/home.html",
        {
            "total_companies": Company.objects.count(),
            "market_quotes": MarketQuote.objects.order_by("-updated_at")[:10],
            "top_gainers": MarketQuote.objects.order_by("-change_percent")[:5],
            "top_losers": MarketQuote.objects.order_by("change_percent")[:5],
        },
    )
