import requests
import urllib.parse

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect

from .models import UpstoxToken


def login(request):
    params = {
        "response_type": "code",
        "client_id": settings.UPSTOX_CLIENT_ID,
        "redirect_uri": settings.UPSTOX_REDIRECT_URI,
        "state": "quantumstock_ai_v2",
    }

    url = (
        "https://api.upstox.com/v2/login/authorization/dialog?"
        + urllib.parse.urlencode(params)
    )

    return redirect(url)


def callback(request):

    code = request.GET.get("code")

    if not code:
        return JsonResponse(
            {"error": "Authorization code missing"},
            status=400,
        )

    response = requests.post(
        "https://api.upstox.com/v2/login/authorization/token",
        headers={
            "accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "code": code,
            "client_id": settings.UPSTOX_CLIENT_ID,
            "client_secret": settings.UPSTOX_CLIENT_SECRET,
            "redirect_uri": settings.UPSTOX_REDIRECT_URI,
            "grant_type": "authorization_code",
        },
        timeout=30,
    )

    data = response.json()

    if "access_token" not in data:
        return JsonResponse(data, status=400)

    UpstoxToken.objects.all().delete()

    UpstoxToken.objects.create(
        access_token=data["access_token"]
    )

    return JsonResponse(
        {
            "status": "success",
            "message": "Access Token Saved",
            "user": data.get("user_name"),
        }
    )
