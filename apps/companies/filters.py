from django.db.models import Q


class CompanyFilter:

    @staticmethod
    def filter_queryset(queryset, request):
        search = request.GET.get("search", "").strip()
        sector = request.GET.get("sector", "").strip()
        industry = request.GET.get("industry", "").strip()
        exchange = request.GET.get("exchange", "").strip()

        if search:
            queryset = queryset.filter(
                Q(symbol__icontains=search)
                | Q(name__icontains=search)
                | Q(sector__icontains=search)
                | Q(industry__icontains=search)
            )

        if sector:
            queryset = queryset.filter(
                sector__iexact=sector
            )

        if industry:
            queryset = queryset.filter(
                industry__iexact=industry
            )

        if exchange:
            queryset = queryset.filter(
                exchange__iexact=exchange
            )

        return queryset
