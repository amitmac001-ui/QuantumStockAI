from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.dashboard.services.dashboard_service import DashboardService
from apps.dashboard.services.stock_detail_service import StockDetailService
from apps.companies.models import Company


class DashboardHomeAPIView(APIView):
    authentication_classes = [SessionAuthentication, JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(DashboardService.home())


class DashboardSearchAPIView(APIView):
    authentication_classes = [SessionAuthentication, JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(DashboardService.search(request.query_params.get("q", "")))


class DashboardStockDetailAPIView(APIView):
    authentication_classes = [SessionAuthentication, JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, symbol):
        try:
            payload = StockDetailService.detail(
                symbol,
                range_code=request.query_params.get("range"),
            )
        except Company.DoesNotExist:
            return Response(
                {"detail": "Stock not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        except ValueError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(payload)


# Kept for imports that used the original class name before the normalized route.
DashboardAPIView = DashboardHomeAPIView
