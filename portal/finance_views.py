from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from claims.donations import issue_confirmation, people_with_waivers
from claims.exports import csv_booking_list, eligible_reports_for_payment, receipts_zip, sepa_pain001
from claims.models import PaymentRun
from claims.payments import create_payment_run, mark_payment_run_paid
from portal.staff_decorators import treasurer_required


@treasurer_required
def finance_home(request):
    return render(
        request,
        "portal/finance_home.html",
        {
            "eligible_count": eligible_reports_for_payment().count(),
            "runs": PaymentRun.objects.order_by("-created_at")[:20],
        },
    )


@treasurer_required
@require_http_methods(["GET", "POST"])
def payment_run_create(request):
    eligible = list(eligible_reports_for_payment())
    if request.method == "POST":
        ids = [int(x) for x in request.POST.getlist("report_ids")]
        note = request.POST.get("note", "")
        try:
            run = create_payment_run(request.user, note=note, report_ids=ids or None)
            messages.success(request, f"Zahlungslauf #{run.pk} angelegt.")
            return redirect("portal:payment_run_detail", pk=run.pk)
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages) if hasattr(exc, "messages") else str(exc))
    return render(request, "portal/payment_run_create.html", {"eligible": eligible})


@treasurer_required
def payment_run_detail(request, pk: int):
    run = get_object_or_404(PaymentRun.objects.prefetch_related("reports__submitter"), pk=pk)
    reports = list(run.reports.all())
    total = sum((r.payout_amount for r in reports), Decimal("0.00"))
    return render(
        request,
        "portal/payment_run_detail.html",
        {"run": run, "reports": reports, "total": total},
    )


@treasurer_required
def payment_run_csv(request, pk: int):
    run = get_object_or_404(PaymentRun, pk=pk)
    data = csv_booking_list(run)
    response = HttpResponse(data, content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="buchungsliste_{run.pk}.csv"'
    return response


@treasurer_required
def payment_run_sepa(request, pk: int):
    run = get_object_or_404(PaymentRun, pk=pk)
    try:
        data = sepa_pain001(run)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("portal:payment_run_detail", pk=pk)
    response = HttpResponse(data, content_type="application/xml")
    response["Content-Disposition"] = f'attachment; filename="sepa_{run.pk}.xml"'
    return response


@treasurer_required
def payment_run_zip(request, pk: int):
    run = get_object_or_404(PaymentRun, pk=pk)
    data = receipts_zip(run)
    response = HttpResponse(data, content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="belege_{run.pk}.zip"'
    return response


@treasurer_required
@require_POST
def payment_run_mark_paid(request, pk: int):
    run = get_object_or_404(PaymentRun, pk=pk)
    try:
        mark_payment_run_paid(request.user, run)
        messages.success(request, "Als überwiesen markiert.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages) if hasattr(exc, "messages") else str(exc))
    return redirect("portal:payment_run_detail", pk=pk)


@treasurer_required
@require_http_methods(["GET", "POST"])
def donations_year(request):
    from django.utils import timezone

    year = int(request.POST.get("year") or request.GET.get("year") or timezone.localdate().year)
    people = list(people_with_waivers(year))
    if request.method == "POST" and "issue" in request.POST:
        person_id = int(request.POST["person_id"])
        from people.models import Person

        person = get_object_or_404(Person, pk=person_id)
        try:
            confirmation = issue_confirmation(person, year, actor=request.user)
            messages.success(
                request,
                f"Zuwendungsbestätigung {year} für {person}: {confirmation.total_amount} €",
            )
        except ValueError as exc:
            messages.error(request, str(exc))
        return redirect(f"{request.path}?year={year}")
    return render(
        request,
        "portal/donations_year.html",
        {"year": year, "people": people},
    )
