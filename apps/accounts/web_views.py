from django.contrib.auth import login, logout
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth import get_user_model
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods, require_POST


class WebsiteSignupForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ("email", "username")


@require_http_methods(["GET", "POST"])
def website_signup(request):
    if request.user.is_authenticated:
        return redirect("dashboard:home")
    form = WebsiteSignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        return redirect("dashboard:home")
    return render(request, "registration/signup.html", {"form": form})


@require_http_methods(["GET", "POST"])
def website_login(request):
    if request.user.is_authenticated:
        return redirect("dashboard:home")

    form = AuthenticationForm(request=request, data=request.POST or None)
    next_url = request.POST.get("next") or request.GET.get("next") or ""
    if request.method == "POST" and form.is_valid():
        login(request, form.get_user())
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(next_url)
        return redirect("dashboard:home")

    return render(
        request,
        "registration/login.html",
        {"form": form, "next": next_url},
    )


@require_POST
def website_logout(request):
    logout(request)
    return redirect(reverse("website-login"))
