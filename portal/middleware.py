from django.shortcuts import redirect

from people.auth_helpers import user_requires_staff_login


class StaffOTPVerifiedMiddleware:
    """Freigeber, Schatzmeister and admins need TOTP before the admin area."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        if path.startswith("/admin/login"):
            return self.get_response(request)
        if path.startswith("/admin/") and request.user.is_authenticated:
            if user_requires_staff_login(request.user) and not request.session.get("otp_verified"):
                return redirect("portal:staff_totp")
        return self.get_response(request)
