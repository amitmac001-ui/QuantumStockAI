import urllib.parse

import requests
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect

from apps.upstox_auth.services.oauth_service import oauth_service


def login(request):
    state = oauth_service.generate_state()
    request.session["oauth_state"] = state

    params = {
        "response_type": "code",
        "client_id": settings.UPSTOX_CLIENT_ID,
        "redirect_uri": settings.UPSTOX_REDIRECT_URI,
        "state": state,
    }

    url = (
        "https://api.upstox.com/v2/login/authorization/dialog?"
        + urllib.parse.urlencode(params)
    )

    return redirect(url)


def callback(request):
    code = request.GET.get("code")
    state = request.GET.get("state")

    if not code:
        return JsonResponse(
            {"error": "Authorization code missing"},
            status=400,
        )

    try:
        oauth_service.validate_state(
            request.session.get("oauth_state"),
            state,
        )
    except Exception as exc:
        return JsonResponse(
            {"error": str(exc)},
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

    oauth_service.save_tokens(
        access_token=data["access_token"],
        refresh_token=data.get("refresh_token"),
        expires_at=None,
    )

    return JsonResponse(
        {
            "status": "success",
            "message": "Authentication successful.",
            "user": data.get("user_name"),
        }
    )
