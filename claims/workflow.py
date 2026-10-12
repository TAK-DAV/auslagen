"""Approval workflow: per-line factual review, treasurer release, questions.

Status path:
ENTWURF → EINGEREICHT → SACHLICH_GEPRUEFT → FREIGEGEBEN
  ↘ Rückfrage aus jeder Prüfstufe → ENTWURF
Vollverzicht: nach FREIGEGEBEN direkt ERLEDIGT (keine Zahlung).
"""

from __future__ import annotations

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from claims.audit import log_change, log_many
from claims.models import (
    DonationChoice,
    ExpenseReport,
    FactualReview,
    LineItem,
    ReportComment,
    ReportStatus,
)
from claims.notifications import (
    notify_approvers_of_submission,
    notify_submitter_approved,
    notify_submitter_question,
    notify_treasurers_ready,
)
from people.roles import APPROVER, TREASURER


def is_treasurer(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name=TREASURER).exists()


def is_approver(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    return user.groups.filter(name=APPROVER).exists() or is_treasurer(user)


def can_factually_review_line(user, line: LineItem) -> bool:
    if not is_approver(user) and not is_treasurer(user):
        return False
    if line.report.submitter_id == user.pk:
        return False
    if line.report.status not in {ReportStatus.SUBMITTED, ReportStatus.REVIEWED}:
        return False
    if is_treasurer(user):
        return True
    return line.cost_center.approvers.filter(pk=user.pk).exists()


def lines_awaiting_factual_review_for(user):
    qs = LineItem.objects.filter(
        report__status=ReportStatus.SUBMITTED,
        factual_review=FactualReview.OPEN,
    ).select_related("report", "cost_center", "report__submitter")
    if is_treasurer(user):
        return qs.exclude(report__submitter=user)
    return qs.filter(cost_center__approvers=user).exclude(report__submitter=user)


def refresh_report_after_factual_reviews(report: ExpenseReport) -> None:
    """When every line is factually approved, move to SACHLICH_GEPRUEFT."""
    lines = list(report.lines.all())
    if not lines:
        return
    if all(line.factual_review == FactualReview.APPROVED for line in lines):
        if report.status == ReportStatus.SUBMITTED:
            old = report.status
            report.status = ReportStatus.REVIEWED
            report.save(update_fields=["status", "updated_at"])
            log_change(
                actor=None,
                obj=report,
                field_name="status",
                old_value=old,
                new_value=report.status,
                reason="Alle Positionen sachlich freigegeben.",
            )
            notify_treasurers_ready(report)


@transaction.atomic
def approve_line_factually(user, line: LineItem, *, note: str = "") -> LineItem:
    if not can_factually_review_line(user, line):
        raise PermissionDenied("Keine Berechtigung für diese Position.")
    if line.factual_review == FactualReview.APPROVED:
        return line
    old = line.factual_review
    line.factual_review = FactualReview.APPROVED
    line.factual_reviewed_by = user
    line.factual_reviewed_at = timezone.now()
    if note:
        line.factual_review_note = note
    line.save(
        update_fields=[
            "factual_review",
            "factual_reviewed_by",
            "factual_reviewed_at",
            "factual_review_note",
        ]
    )
    log_many(
        actor=user,
        obj=line,
        changes={
            "factual_review": (old, line.factual_review),
            "factual_reviewed_by": (None, user.email),
        },
        reason=note or "Sachliche Freigabe",
    )
    refresh_report_after_factual_reviews(line.report)
    return line


@transaction.atomic
def send_back_with_question(user, report: ExpenseReport, *, body: str, line: LineItem | None = None) -> ReportComment:
    if report.status not in {
        ReportStatus.SUBMITTED,
        ReportStatus.REVIEWED,
        ReportStatus.APPROVED,
    }:
        raise ValidationError("In diesem Status gibt es keine Rückfrage.")
    if report.submitter_id == user.pk:
        raise PermissionDenied("Eigene Abrechnungen kann man nicht zurückfragen.")
    if not (is_approver(user) or is_treasurer(user)):
        raise PermissionDenied("Keine Berechtigung.")
    if line is not None and not can_factually_review_line(user, line) and not is_treasurer(user):
        raise PermissionDenied("Keine Berechtigung für diese Position.")
    if not (body or "").strip():
        raise ValidationError("Der Kommentar zur Rückfrage fehlt.")

    old_status = report.status
    comment = ReportComment.objects.create(report=report, author=user, body=body.strip())
    if line is not None:
        old_review = line.factual_review
        line.factual_review = FactualReview.QUESTION
        line.factual_review_note = body.strip()
        line.factual_reviewed_by = user
        line.factual_reviewed_at = timezone.now()
        line.save(
            update_fields=[
                "factual_review",
                "factual_review_note",
                "factual_reviewed_by",
                "factual_reviewed_at",
            ]
        )
        log_change(
            actor=user,
            obj=line,
            field_name="factual_review",
            old_value=old_review,
            new_value=line.factual_review,
            reason=body.strip(),
        )

    # Reset open approvals so the next submission is reviewed again.
    report.lines.filter(factual_review=FactualReview.APPROVED).update(
        factual_review=FactualReview.OPEN,
        factual_reviewed_by=None,
        factual_reviewed_at=None,
    )
    report.status = ReportStatus.DRAFT
    report.submitted_at = None
    report.save(update_fields=["status", "submitted_at", "updated_at"])
    log_change(
        actor=user,
        obj=report,
        field_name="status",
        old_value=old_status,
        new_value=report.status,
        reason=body.strip(),
    )
    notify_submitter_question(report, comment)
    return comment


@transaction.atomic
def treasurer_approve(user, report: ExpenseReport, *, reason: str = "") -> ExpenseReport:
    if not is_treasurer(user):
        raise PermissionDenied("Nur der Schatzmeister gibt final frei.")
    if report.submitter_id == user.pk:
        raise PermissionDenied("Eigene Abrechnungen kann niemand selbst freigeben.")
    if report.status != ReportStatus.REVIEWED:
        raise ValidationError("Die Abrechnung ist noch nicht vollständig sachlich geprüft.")
    open_lines = report.lines.exclude(factual_review=FactualReview.APPROVED)
    if open_lines.exists():
        raise ValidationError("Es sind noch Positionen ohne sachliche Freigabe offen.")

    old = report.status
    if report.donation_choice == DonationChoice.FULL and report.payout_amount == 0:
        report.status = ReportStatus.DONE
    else:
        report.status = ReportStatus.APPROVED
    report.save(update_fields=["status", "updated_at"])
    log_change(
        actor=user,
        obj=report,
        field_name="status",
        old_value=old,
        new_value=report.status,
        reason=reason or "Finale Freigabe durch Schatzmeister",
    )
    notify_submitter_approved(report)
    return report


def mark_submitted(report: ExpenseReport) -> None:
    """Call after a successful submit from the portal."""
    notify_approvers_of_submission(report)
    log_change(
        actor=report.submitter,
        obj=report,
        field_name="status",
        old_value=ReportStatus.DRAFT,
        new_value=ReportStatus.SUBMITTED,
        reason="Eingereicht",
    )
