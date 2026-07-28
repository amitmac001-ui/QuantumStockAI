from django.db.models import Count

from rest_framework import generics, permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from .filters import CompanyFilter
from .models import Company
from .pagination import CompanyPagination
from .serializers import (
    CompanyDetailSerializer,
    CompanyListSerializer,
)


class CompanyListView(generics.ListAPIView):
    permission_classes = [
        permissions.IsAuthenticated,
    ]

    serializer_class = CompanyListSerializer

    pagination_class = CompanyPagination

    queryset = (
        Company.objects.filter(
            is_active=True,
        )
        .only(
            "id",
            "symbol",
            "name",
            "exchange",
            "sector",
            "industry",
            "market_cap",
        )
    )

    def get_queryset(self):
        queryset = CompanyFilter.filter_queryset(
            self.queryset,
            self.request,
        )

        ordering = self.request.GET.get(
            "ordering",
            "symbol",
        )

        allowed = {
            "symbol",
            "-symbol",
            "name",
            "-name",
            "market_cap",
            "-market_cap",
            "sector",
            "-sector",
            "industry",
            "-industry",
        }

        if ordering not in allowed:
            ordering = "symbol"

        return queryset.order_by(ordering)


class CompanyDetailView(generics.RetrieveAPIView):
    authentication_classes = []
    permission_classes = [
        permissions.AllowAny,
    ]

    serializer_class = CompanyDetailSerializer
    lookup_field = "symbol"

    queryset = Company.objects.filter(
        is_active=True,
    )


class CompanyStatsView(APIView):
    permission_classes = [
        permissions.AllowAny,
    ]

    def get(self, request):
        queryset = Company.objects.filter(
            is_active=True,
        )

        return Response(
            {
                "success": True,
                "data": {
                    "total_companies": queryset.count(),
                    "total_sectors": queryset.exclude(
                        sector=""
                    ).values(
                        "sector"
                    ).distinct().count(),
                    "total_industries": queryset.exclude(
                        industry=""
                    ).values(
                        "industry"
                    ).distinct().count(),
                    "exchange_distribution": list(
                        queryset.values(
                            "exchange"
                        ).annotate(
                            total=Count("id")
                        ).order_by(
                            "exchange"
                        )
                    ),
                },
            }
        )
