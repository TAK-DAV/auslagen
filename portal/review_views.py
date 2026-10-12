from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from claims.models import ExpenseReport, FactualReview, LineItem, ReportStatus
from claims.workflow import (
    approve_line_factually,
    can_factually_review_line,
    is_approver,
    is_treasurer,
    lines_awaiting_factual_review_for,
    send_back_with_question,
    treasurer_approve,
)
from portal.staff_decorators import approver_required, staff_otp_required, treasurer_required


@staff_otp_required
def team_home(request):
    awaiting = []
    if is_approver(request.user):
        awaiting = list(lines_awaiting_factual_review_for(request.user)[:50])
    treasurer_queue = []
    if is_treasurer(request.user):
        treasurer_queue = list(
            ExpenseReport.objects.filter(status=ReportStatus.REVIEWED)
            .exclude(submitter=request.user)
            .select_related("submitter")[:50]
        )
    return render(
        request,
        "portal/team_home.html",
        {
            "awaiting": awaiting,
            "treasurer_queue": treasurer_queue,
            "is_approver": is_approver(request.user),
            "is_treasurer": is_treasurer(request.user),
        },
    )


@approver_required
def review_queue(request):
    lines = lines_awaiting_factual_review_for(request.user)
    return render(request, "portal/review_queue.html", {"lines": lines})


@approver_required
def review_report(request, pk: int):
    report = get_object_or_404(
        ExpenseReport.objects.select_related("submitter"),
        pk=pk,
        status__in=[ReportStatus.SUBMITTED, ReportStatus.REVIEWED],
    )
    lines = report.lines.select_related("cost_center", "receipt").all()
    actionable = [
        line for line in lines if can_factually_review_line(request.user, line)
    ]
    comments = report.comments.select_related("author").all()
    return render(
        request,
        "portal/review_report.html",
        {
            "report": report,
            "lines": lines,
            "actionable": actionable,
            "comments": comments,
            "can_question": bool(actionable) or is_treasurer(request.user),
        },
    )


@approver_required
@require_POST
def review_approve_line(request, report_pk: int, line_pk: int):
    line = get_object_or_404(LineItem, pk=line_pk, report_id=report_pk)
    note = request.POST.get("note", "")
    try:
        approve_line_factually(request.user, line, note=note)
        messages.success(request, "Position sachlich freigegeben.")
    except (PermissionDenied, ValidationError) as exc:
        messages.error(request, str(exc))
    return redirect("portal:review_report", pk=report_pk)


@approver_required
@require_http_methods(["GET", "POST"])
def review_question(request, pk: int):
    report = get_object_or_404(
        ExpenseReport,
        pk=pk,
        status__in=[ReportStatus.SUBMITTED, ReportStatus.REVIEWED, ReportStatus.APPROVED],
    )
    line_id = request.GET.get("line") or request.POST.get("line")
    line = None
    if line_id:
        line = get_object_or_404(LineItem, pk=line_id, report=report)
    if request.method == "POST":
        body = request.POST.get("body", "")
        try:
            send_back_with_question(request.user, report, body=body, line=line)
            messages.info(request, "Rückfrage gesendet. Die Abrechnung ist wieder Entwurf.")
            return redirect("portal:review_queue")
        except (PermissionDenied, ValidationError) as exc:
            messages.error(request, str(exc))
    return render(
        request,
        "portal/review_question.html",
        {"report": report, "line": line},
    )


@treasurer_required
def treasurer_queue(request):
    reports = (
        ExpenseReport.objects.filter(status=ReportStatus.REVIEWED)
        .exclude(submitter=request.user)
        .select_related("submitter")
        .prefetch_related("lines")
    )
    return render(request, "portal/treasurer_queue.html", {"reports": reports})


@treasurer_required
def treasurer_report(request, pk: int):
    report = get_object_or_404(
        ExpenseReport.objects.select_related("submitter"),
        pk=pk,
        status=ReportStatus.REVIEWED,
    )
    lines = report.lines.select_related("cost_center", "sphere", "tax_rate").all()
    comments = report.comments.select_related("author").all()
    return render(
        request,
        "portal/treasurer_report.html",
        {
            "report": report,
            "lines": lines,
            "comments": comments,
            "vat_totals": report.vat_totals(),
            "all_approved": all(
                line.factual_review == FactualReview.APPROVED for line in lines
            ),
        },
    )


@treasurer_required
@require_POST
def treasurer_approve_view(request, pk: int):
    report = get_object_or_404(ExpenseReport, pk=pk)
    reason = request.POST.get("reason", "")
    try:
        treasurer_approve(request.user, report, reason=reason)
        messages.success(request, f"Abrechnung #{report.pk} freigegeben ({report.get_status_display()}).")
        return redirect("portal:treasurer_queue")
    except (PermissionDenied, ValidationError) as exc:
        messages.error(request, str(exc))
        return redirect("portal:treasurer_report", pk=pk)
