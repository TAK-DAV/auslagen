"""Create and close payment runs."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from claims.audit import log_change
from claims.exports import eligible_reports_for_payment
from claims.models import ExpenseReport, PaymentRun, ReportStatus


@transaction.atomic
def create_payment_run(user, *, note: str = "", report_ids: list[int] | None = None) -> PaymentRun:
    qs = eligible_reports_for_payment()
    if report_ids is not None:
        qs = qs.filter(pk__in=report_ids)
    reports = list(qs)
    if not reports:
        raise ValidationError("Keine freigegebenen Abrechnungen mit Auszahlungsbetrag.")
    for report in reports:
        if report.payout_amount <= 0:
            raise ValidationError(f"Abrechnung {report.pk} hat keinen Auszahlungsbetrag.")
        if not (report.submitter.iban or "").strip():
            raise ValidationError(f"IBAN fehlt bei Abrechnung {report.pk}.")

    run = PaymentRun.objects.create(created_by=user, note=note or "")
    for report in reports:
        old = report.status
        report.status = ReportStatus.IN_PAYMENT
        report.payment_run = run
        report.save(update_fields=["status", "payment_run", "updated_at"])
        log_change(
            actor=user,
            obj=report,
            field_name="status",
            old_value=old,
            new_value=report.status,
            reason=f"Zahlungslauf {run.pk}",
        )
    return run


@transaction.atomic
def mark_payment_run_paid(user, payment_run: PaymentRun) -> PaymentRun:
    if payment_run.marked_paid_at:
        raise ValidationError("Dieser Lauf ist bereits als überwiesen markiert.")
    payment_run.marked_paid_at = timezone.now()
    payment_run.save(update_fields=["marked_paid_at"])
    for report in payment_run.reports.all():
        old = report.status
        report.status = ReportStatus.PAID
        report.save(update_fields=["status", "updated_at"])
        log_change(
            actor=user,
            obj=report,
            field_name="status",
            old_value=old,
            new_value=report.status,
            reason=f"Zahlungslauf {payment_run.pk} als überwiesen markiert",
        )
    return payment_run
