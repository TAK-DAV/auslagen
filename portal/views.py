from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.views import redirect_to_login
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from claims.models import DonationChoice, ExpenseReport, FactualReview, LineItem, ReportStatus
from masterdata.models import TaxRate
from people.auth_helpers import user_can_submit_expenses, user_requires_staff_login
from people.magic_link import consume_login_token, create_login_token, send_magic_link_email
from people.models import Person
from portal.decorators import submitter_required
from portal.forms import LineItemForm, LoginRequestForm, PrivacyForm, ProfileForm, SubmitReportForm, StaffLoginForm


def _draft_report_for(user, pk):
    report = get_object_or_404(ExpenseReport, pk=pk, submitter=user)
    if report.status != ReportStatus.DRAFT:
        raise Http404
    return report


@require_http_methods(["GET", "POST"])
def login_request(request):
    if request.user.is_authenticated and user_can_submit_expenses(request.user):
        return redirect("portal:report_list")
    form = LoginRequestForm(request.POST or None)
    sent = False
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"].lower()
        user = Person.objects.filter(email=email, is_active=True).first()
        if user and not user_requires_staff_login(user):
            raw = create_login_token(user)
            send_magic_link_email(user, raw)
        sent = True
    return render(request, "portal/login_request.html", {"form": form, "sent": sent})


def magic_login(request, token: str):
    user = consume_login_token(token)
    if user is None:
        messages.error(request, "Der Link ist ungültig oder abgelaufen. Bitte einen neuen anfordern.")
        return redirect("portal:login_request")
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    if not user.privacy_acknowledged:
        return redirect("portal:privacy")
    return redirect("portal:report_list")


@require_http_methods(["GET", "POST"])
def privacy(request):
    if not request.user.is_authenticated:
        return redirect("portal:login_request")
    if not user_can_submit_expenses(request.user):
        return redirect("portal:staff_login")
    if request.user.privacy_acknowledged:
        return redirect("portal:report_list")
    form = PrivacyForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        request.user.privacy_acknowledged_at = timezone.now()
        request.user.save(update_fields=["privacy_acknowledged_at"])
        return redirect("portal:report_list")
    return render(request, "portal/privacy.html", {"form": form})


@require_POST
def portal_logout(request):
    logout(request)
    return redirect("home")


@submitter_required
def report_list(request):
    reports = ExpenseReport.objects.filter(submitter=request.user).order_by("-updated_at")
    return render(request, "portal/report_list.html", {"reports": reports})


@submitter_required
@require_POST
def report_create(request):
    report = ExpenseReport.objects.create(submitter=request.user, status=ReportStatus.DRAFT)
    return redirect("portal:report_detail", pk=report.pk)


@submitter_required
def report_detail(request, pk: int):
    report = get_object_or_404(ExpenseReport, pk=pk, submitter=request.user)
    lines = report.lines.select_related("cost_center", "receipt").all()
    readonly = report.status != ReportStatus.DRAFT
    return render(
        request,
        "portal/report_detail.html",
        {"report": report, "lines": lines, "readonly": readonly},
    )


@submitter_required
@require_http_methods(["GET", "POST"])
def line_create(request, report_pk: int):
    report = _draft_report_for(request.user, report_pk)
    form = LineItemForm(request.POST or None, request.FILES or None, report=report)
    if request.method == "POST" and form.is_valid():
        line = form.save()
        errors = line.submission_errors()
        if errors:
            for message in errors:
                messages.warning(request, message)
        messages.success(request, "Position wurde gespeichert.")
        return redirect("portal:report_detail", pk=report.pk)
    return render(request, "portal/line_form.html", {"form": form, "report": report})


@submitter_required
@require_POST
def line_delete(request, report_pk: int, line_pk: int):
    report = _draft_report_for(request.user, report_pk)
    line = get_object_or_404(LineItem, pk=line_pk, report=report)
    line.delete()
    messages.info(request, "Position entfernt.")
    return redirect("portal:report_detail", pk=report.pk)


@submitter_required
@require_http_methods(["GET", "POST"])
def report_submit(request, pk: int):
    report = _draft_report_for(request.user, pk)
    form = SubmitReportForm(request.POST or None, report=report)
    if request.method == "POST" and form.is_valid():
        report.donation_choice = form.cleaned_data["donation_choice"]
        report.waiver_amount = form.cleaned_data.get("waiver_amount")
        report.waiver_confirmed = form.cleaned_data.get("waiver_confirmed") or False
        if report.donation_choice in {DonationChoice.PARTIAL, DonationChoice.FULL}:
            report.waiver_at = timezone.now()
        else:
            report.waiver_amount = None
            report.waiver_confirmed = False
            report.waiver_at = None
        errors = report.submission_errors()
        if errors:
            for message in errors:
                messages.error(request, message)
        else:
            for warning in report.waiver_warnings():
                messages.warning(request, warning)
            # Fresh review after a Rückfrage: clear previous line approvals.
            report.lines.exclude(factual_review=FactualReview.OPEN).update(
                factual_review=FactualReview.OPEN,
                factual_reviewed_by=None,
                factual_reviewed_at=None,
            )
            report.status = ReportStatus.SUBMITTED
            report.submitted_at = timezone.now()
            report.save()
            from claims.workflow import mark_submitted

            mark_submitted(report)
            messages.success(request, "Abrechnung eingereicht. Sie wird nun geprüft.")
            return redirect("portal:report_detail", pk=report.pk)
    elif request.method == "GET":
        errors = report.submission_errors()
        for message in errors:
            messages.error(request, message)
    return render(request, "portal/report_submit.html", {"report": report, "form": form})


@submitter_required
@require_http_methods(["GET", "POST"])
def profile_edit(request):
    form = ProfileForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Profil gespeichert.")
        return redirect("portal:report_list")
    return render(request, "portal/profile.html", {"form": form})


@require_http_methods(["GET", "POST"])
def staff_login(request):
    if request.user.is_authenticated and user_requires_staff_login(request.user):
        return redirect("portal:staff_totp")
    form = StaffLoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = authenticate(
            request,
            username=form.cleaned_data["email"].lower(),
            password=form.cleaned_data["password"],
        )
        if user is None or not user.is_active or not user_requires_staff_login(user):
            messages.error(request, "Anmeldung fehlgeschlagen.")
        else:
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            request.session["otp_verified"] = False
            return redirect("portal:staff_totp")
    return render(request, "portal/staff_login.html", {"form": form})


@require_http_methods(["GET", "POST"])
def staff_totp(request):
    if not request.user.is_authenticated or not user_requires_staff_login(request.user):
        return redirect_to_login(request.get_full_path(), login_url="portal:staff_login")
    from django_otp.plugins.otp_totp.models import TOTPDevice

    device = TOTPDevice.objects.filter(user=request.user, confirmed=True).first()
    if request.method == "POST" and "token" in request.POST:
        from django_otp import match_token

        if match_token(request.user, request.POST.get("token", "")):
            request.session["otp_verified"] = True
            messages.success(request, "Zwei-Faktor-Anmeldung erfolgreich.")
            return redirect("portal:team_home")
        messages.error(request, "Der Code war nicht korrekt.")
    if not device:
        return render(request, "portal/staff_totp_setup.html", _totp_setup_context(request))
    if request.session.get("otp_verified"):
        return redirect("portal:team_home")
    return render(request, "portal/staff_totp_verify.html")


def _totp_setup_context(request):
    from django_otp.plugins.otp_totp.models import TOTPDevice

    device, _created = TOTPDevice.objects.get_or_create(
        user=request.user, name="default", defaults={"confirmed": False}
    )
    if not device.key:
        device.save()
    config_url = device.config_url
    return {"config_url": config_url, "device": device}


@require_POST
def staff_totp_confirm_setup(request):
    if not request.user.is_authenticated:
        return HttpResponseForbidden()
    from django_otp.plugins.otp_totp.models import TOTPDevice

    device = TOTPDevice.objects.filter(user=request.user, confirmed=False).first()
    token = request.POST.get("token", "")
    if device and device.verify_token(token):
        device.confirmed = True
        device.save()
        request.session["otp_verified"] = True
        messages.success(request, "Authenticator eingerichtet.")
        return redirect("portal:team_home")
    messages.error(request, "Der Code war nicht korrekt. Bitte erneut versuchen.")
    return redirect("portal:staff_totp")


def tax_rates_partial(request):
    country = request.GET.get("country", "")
    if country not in {"DE", "AT"}:
        return render(request, "portal/partials/tax_rate_options.html", {"rates": []})
    rates = TaxRate.objects.filter(country=country).order_by("-rate_percent")
    return render(request, "portal/partials/tax_rate_options.html", {"rates": rates})
