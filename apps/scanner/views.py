from rest_framework.permissions import AllowAny

from apps.core.views.base import BaseAPIView
from apps.scanner.serializers import (
    ScanResultSerializer,
    ScannerSerializer,
)
from apps.scanner.services.scanner_service import ScannerService


class TopGainersAPIView(BaseAPIView):

    permission_classes = [AllowAny]

    def get(self, request):

        queryset = ScannerService.top_gainers()

        serializer = ScannerSerializer(
            queryset,
            many=True,
        )

        return self.success(
            data=serializer.data,
        )


class TopLosersAPIView(BaseAPIView):

    permission_classes = [AllowAny]

    def get(self, request):

        queryset = ScannerService.top_losers()

        serializer = ScannerSerializer(
            queryset,
            many=True,
        )

        return self.success(
            data=serializer.data,
        )


class MostActiveAPIView(BaseAPIView):

    permission_classes = [AllowAny]

    def get(self, request):

        queryset = ScannerService.most_active()

        serializer = ScannerSerializer(
            queryset,
            many=True,
        )

        return self.success(
            data=serializer.data,
        )


class ScannerAPIView(BaseAPIView):

    permission_classes = [AllowAny]

    def get(self, request, symbol):

        data = ScannerService.scan(symbol.upper())

        serializer = ScanResultSerializer(data)

        return self.success(
            data=serializer.data,
        )
