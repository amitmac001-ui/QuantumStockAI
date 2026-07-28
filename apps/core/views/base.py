from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.core.api.response import APIResponse


class BaseAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def success(
        self,
        data=None,
        message="Success",
        status_code=200,
    ):
        return APIResponse.success(
            data=data,
            message=message,
            status_code=status_code,
        )

    def error(
        self,
        message="Error",
        errors=None,
        status_code=400,
    ):
        return APIResponse.error(
            message=message,
            errors=errors,
            status_code=status_code,
        )
