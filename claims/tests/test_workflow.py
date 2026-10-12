from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from django.core import mail
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from claims.models import (
    AuditLog,
    DonationChoice,
    ExpenseReport,
    FactualReview,
    LineItem,
    Receipt,
    ReportStatus,
)
from claims.workflow import (
    approve_line_factually,
    can_factually_review_line,
    mark_submitted,
    send_back_with_question,
    treasurer_approve,
)
from masterdata.constants import Area, Country, ExpenseType
from masterdata.models import CostCenter, Hut, TaxRate
from people.models import Person
from people.roles import APPROVER, TREASURER


@pytest.fixture
def actors(db, seeded):
    submitter = Person.objects.create_user(
        "eva@example.org",
        password="x",
        first_name="Eva",
        last_name="Berg",
        iban="DE89370400440532013000",
    )
    approver = Person.objects.create_user(
        "freigabe@example.org",
        password="secret-pass-1",
        first_name="Fritz",
        last_name="Frei",
    )
    treasurer = Person.objects.create_user(
        "schatz@example.org",
        password="secret-pass-1",
        first_name="Susi",
        last_name="Schatz",
        is_staff=True,
    )
    Group.objects.get_or_create(name=APPROVER)
    Group.objects.get_or_create(name=TREASURER)
    approver.groups.add(Group.objects.get(name=APPROVER))
    treasurer.groups.add(Group.objects.get(name=TREASURER))
    center = CostCenter.objects.get(name="Rotwandhaus Betrieb")
    center.approvers.add(approver)
    return {"submitter": submitter, "approver": approver, "treasurer": treasurer, "center": center}


def _submitted_report(submitter, center):
    report = ExpenseReport.objects.create(
        submitter=submitter,
        status=ReportStatus.SUBMITTED,
        submitted_at=timezone.now(),
        donation_choice=DonationChoice.PAYOUT,
    )
    receipt = Receipt.objects.create(
        report=report,
        file=SimpleUploadedFile("b.jpg", b"x", content_type="image/jpeg"),
    )
    de19 = TaxRate.objects.get(country=Country.DE, rate_percent=Decimal("19.00"))
    LineItem.objects.create(
        report=report,
        expense_type=ExpenseType.HUT_MATERIAL,
        expense_date=date(2026, 6, 1),
        cost_center=center,
        hut=Hut.objects.get(name="Rotwandhaus"),
        area=Area.OPERATION,
        usage="Farbe",
        receipt=receipt,
        receipt_country=Country.DE,
        tax_rate=de19,
        gross=Decimal("119.00"),
    )
    return report


@pytest.mark.django_db
def test_submitter_cannot_approve_own_line(actors):
    report = _submitted_report(actors["submitter"], actors["center"])
    line = report.lines.get()
    assert can_factually_review_line(actors["submitter"], line) is False
    with pytest.raises(PermissionDenied):
        approve_line_factually(actors["submitter"], line)


@pytest.mark.django_db
def test_approver_then_treasurer_full_path(actors, settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    mail.outbox.clear()
    report = _submitted_report(actors["submitter"], actors["center"])
    mark_submitted(report)
    assert any("sachlichen Prüfung" in m.subject for m in mail.outbox)

    line = report.lines.get()
    approve_line_factually(actors["approver"], line, note="passt")
    line.refresh_from_db()
    report.refresh_from_db()
    assert line.factual_review == FactualReview.APPROVED
    assert report.status == ReportStatus.REVIEWED
    assert AuditLog.objects.filter(field_name="factual_review").exists()
    assert any("finale Freigabe" in m.subject or "freigeben" in m.subject for m in mail.outbox)

    treasurer_approve(actors["treasurer"], report)
    report.refresh_from_db()
    assert report.status == ReportStatus.APPROVED
    assert any("freigegeben" in m.subject for m in mail.outbox)


@pytest.mark.django_db
def test_full_waiver_ends_in_done(actors):
    report = _submitted_report(actors["submitter"], actors["center"])
    report.donation_choice = DonationChoice.FULL
    report.waiver_confirmed = True
    report.waiver_at = timezone.now()
    report.save()
    actors["submitter"].street = "A 1"
    actors["submitter"].postal_code = "83022"
    actors["submitter"].city = "Rosenheim"
    actors["submitter"].address_country = "DE"
    actors["submitter"].save()
    line = report.lines.get()
    approve_line_factually(actors["approver"], line)
    report.refresh_from_db()
    treasurer_approve(actors["treasurer"], report)
    report.refresh_from_db()
    assert report.payout_amount == Decimal("0.00")
    assert report.status == ReportStatus.DONE


@pytest.mark.django_db
def test_question_returns_to_draft_and_mails_submitter(actors, settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    mail.outbox.clear()
    report = _submitted_report(actors["submitter"], actors["center"])
    line = report.lines.get()
    send_back_with_question(
        actors["approver"],
        report,
        body="Bitte Teilnehmer ergänzen.",
        line=line,
    )
    report.refresh_from_db()
    line.refresh_from_db()
    assert report.status == ReportStatus.DRAFT
    assert report.submitted_at is None
    assert line.factual_review == FactualReview.QUESTION
    assert report.comments.count() == 1
    assert any("Rückfrage" in m.subject for m in mail.outbox)
    assert actors["submitter"].email in mail.outbox[-1].to


@pytest.mark.django_db
def test_approver_for_other_cost_center_blocked(actors):
    other = Person.objects.create_user("fremd@example.org", password="x")
    other.groups.add(Group.objects.get(name=APPROVER))
    report = _submitted_report(actors["submitter"], actors["center"])
    line = report.lines.get()
    assert can_factually_review_line(other, line) is False
    with pytest.raises(PermissionDenied):
        approve_line_factually(other, line)


@pytest.mark.django_db
def test_treasurer_cannot_approve_before_factual_review(actors):
    report = _submitted_report(actors["submitter"], actors["center"])
    with pytest.raises(ValidationError):
        treasurer_approve(actors["treasurer"], report)
