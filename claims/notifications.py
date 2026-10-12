"""E-mail notices for the approval workflow. Failures are logged, not raised."""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


def _send(subject: str, template: str, context: dict, recipients: list[str]) -> None:
    recipients = [r for r in recipients if r]
    if not recipients:
        return
    body = render_to_string(template, context)
    try:
        send_mail(
            subject,
            body,
            settings.DEFAULT_FROM_EMAIL,
            recipients,
            fail_silently=False,
        )
    except Exception:  # noqa: BLE001 - workflow must not die on mail failures
        logger.exception("E-Mail fehlgeschlagen: %s → %s", subject, recipients)


def site_url(path: str = "") -> str:
    return settings.SITE_URL.rstrip("/") + path


def notify_approvers_of_submission(report) -> None:
    from masterdata.models import CostCenter

    cost_center_ids = report.lines.values_list("cost_center_id", flat=True).distinct()
    emails = set()
    for center in CostCenter.objects.filter(pk__in=cost_center_ids).prefetch_related("approvers"):
        for person in center.approvers.filter(is_active=True):
            if person.pk != report.submitter_id:
                emails.add(person.email)
    _send(
        f"Neue Abrechnung #{report.pk} zur sachlichen Prüfung",
        "email/report_submitted.txt",
        {"report": report, "url": site_url(f"/einreichen/pruefung/{report.pk}/")},
        sorted(emails),
    )


def notify_submitter_question(report, comment) -> None:
    _send(
        f"Rückfrage zu Abrechnung #{report.pk}",
        "email/report_question.txt",
        {
            "report": report,
            "comment": comment,
            "url": site_url(f"/einreichen/abrechnungen/{report.pk}/"),
        },
        [report.submitter.email],
    )


def notify_treasurers_ready(report) -> None:
    from django.contrib.auth.models import Group

    from people.roles import TREASURER

    group = Group.objects.filter(name=TREASURER).first()
    emails = []
    if group:
        emails = list(group.user_set.filter(is_active=True).values_list("email", flat=True))
    _send(
        f"Abrechnung #{report.pk} sachlich geprüft – bitte freigeben",
        "email/report_ready_for_treasurer.txt",
        {"report": report, "url": site_url(f"/einreichen/schatzmeister/{report.pk}/")},
        emails,
    )


def notify_submitter_approved(report) -> None:
    _send(
        f"Abrechnung #{report.pk} freigegeben",
        "email/report_approved.txt",
        {
            "report": report,
            "url": site_url(f"/einreichen/abrechnungen/{report.pk}/"),
        },
        [report.submitter.email],
    )
