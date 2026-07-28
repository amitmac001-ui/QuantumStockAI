from django.urls import path

from .views import login, callback

urlpatterns = [
    path("login/", login, name="upstox-login"),
    path("callback/", callback, name="upstox-callback"),
]
