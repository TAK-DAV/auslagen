from django.shortcuts import redirect

from people.auth_helpers import user_requires_staff_login

_PROTECTED_PREFIXES = (
    "/admin/",
    "/einreichen/pruefung/",
    "/einreichen/schatzmeister/",
    "/einreichen/team/",
)

_OTP_EXEMPT_PREFIXES = (
    "/admin/login",
    "/einreichen/team/anmelden/",
    "/einreichen/team/2fa/",
)


class StaffOTPVerifiedMiddleware:
    """Freigeber, Schatzmeister and admins need TOTP before team and admin areas."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        if any(path.startswith(p) for p in _OTP_EXEMPT_PREFIXES):
            return self.get_response(request)
        protected = any(path.startswith(p) for p in _PROTECTED_PREFIXES)
        if protected and request.user.is_authenticated:
            if user_requires_staff_login(request.user) and not request.session.get("otp_verified"):
                return redirect("portal:staff_totp")
        return self.get_response(request)
