from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.shortcuts import redirect

from people.auth_helpers import user_can_submit_expenses


def submitter_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path(), login_url="portal:login_request")
        if not user_can_submit_expenses(request.user):
            return redirect("portal:staff_login")
        if not request.user.privacy_acknowledged:
            return redirect("portal:privacy")
        return view_func(request, *args, **kwargs)

    return wrapper
