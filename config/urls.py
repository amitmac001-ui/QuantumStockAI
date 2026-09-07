"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.core.cache import cache
from django.db import connections
from django.http import JsonResponse
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)
from apps.accounts.web_views import website_login, website_logout


def health_check(request):
    return JsonResponse(
        {
            "status": "ok",
            "application": "QuantumStock AI",
            "version": "2.0.0",
        }
    )


def readiness_check(request):
    checks = {"postgresql": False, "redis": False}
    try:
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1")
            checks["postgresql"] = cursor.fetchone() == (1,)
    except Exception:
        pass
    try:
        key = "health:readiness"
        cache.set(key, "ok", timeout=10)
        checks["redis"] = cache.get(key) == "ok"
        cache.delete(key)
    except Exception:
        pass
    ready = all(checks.values())
    return JsonResponse(
        {"status": "ready" if ready else "unavailable", "checks": checks},
        status=200 if ready else 503,
    )


urlpatterns = [

    path("login/", website_login, name="website-login"),
    path("logout/", website_logout, name="website-logout"),

    path(
       "api/v1/dashboard/",
       include("apps.dashboard.api.urls"),
    ),
   
    path("", include("apps.dashboard.urls")),
   
    path(
        "admin/",
        admin.site.urls,
    ),

    path(
        "api/v1/market/",
        include("apps.market.api.urls"),
    ),

    path(
        "health/",
        health_check,
    ),

    path(
        "ready/",
        readiness_check,
    ),

    path(
        "api/schema/",
        SpectacularAPIView.as_view(),
        name="schema",
    ),

    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(
            url_name="schema",
        ),
        name="swagger-ui",
    ),

    path(
        "api/redoc/",
        SpectacularRedocView.as_view(
            url_name="schema",
        ),
        name="redoc",
    ),

    path(
        "api/v1/accounts/",
        include("apps.accounts.urls"),
    ),

    path(
        "api/v1/companies/",
        include("apps.companies.urls"),
    ),

    path(
        "api/v1/market/",
        include("apps.market.urls"),
    ),

    path(
        "api/v1/scanner/",
        include("apps.scanner.urls"),

    ),

    path(
        "api/v1/upstox/",
        include("apps.upstox_auth.urls"),
    ),

    path(
        "companies/",
        include(
            (
                "apps.companies.urls",
                "companies",
            ),
            namespace="public_companies",
        ),
    ),

]
