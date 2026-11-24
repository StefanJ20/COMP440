from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import redirect, render

from .forms import RegistrationForm, normalize_phone
from .models import BaseUser


def register_view(request):
    if request.user.is_authenticated:
        return redirect("index")

    form = RegistrationForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)

        return redirect("index")

    return render(
        request,
        "register.html",
        {"form": form},
    )


def login_view(request):
    if request.user.is_authenticated:
        return redirect("index")

    error = None

    if request.method == "POST":
        identifier = request.POST.get(
            "identifier",
            "",
        ).strip()

        password = request.POST.get("password", "")

        phone = None

        try:
            phone = normalize_phone(identifier)
        except Exception:
            pass

        lookup = (
            Q(username__iexact=identifier)
            | Q(email__iexact=identifier)
        )

        if phone:
            lookup |= Q(phone_number=phone)

        user = (
            BaseUser.objects
            .filter(lookup)
            .order_by("id")
            .first()
        )

        if (
            user
            and user.check_password(password)
            and user.is_active
        ):
            login(request, user)
            return redirect("index")

        error = (
            "Invalid username, email, phone number, or password."
        )

    return render(
        request,
        "login.html",
        {"error": error},
    )


def logout_view(request):
    logout(request)
    return redirect("login")


@login_required(login_url="login")
def index(request):
    return render(request, "index.html")