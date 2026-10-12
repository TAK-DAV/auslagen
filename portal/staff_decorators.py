from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.shortcuts import redirect

from claims.workflow import is_approver, is_treasurer
from people.auth_helpers import user_requires_staff_login


def staff_otp_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated or not user_requires_staff_login(request.user):
            return redirect_to_login(request.get_full_path(), login_url="portal:staff_login")
        if not request.session.get("otp_verified"):
            return redirect("portal:staff_totp")
        return view_func(request, *args, **kwargs)

    return wrapper


def approver_required(view_func):
    @wraps(view_func)
    @staff_otp_required
    def wrapper(request, *args, **kwargs):
        if not is_approver(request.user):
            return redirect("portal:team_home")
        return view_func(request, *args, **kwargs)

    return wrapper


def treasurer_required(view_func):
    @wraps(view_func)
    @staff_otp_required
    def wrapper(request, *args, **kwargs):
        if not is_treasurer(request.user):
            return redirect("portal:team_home")
        return view_func(request, *args, **kwargs)

    return wrapper
