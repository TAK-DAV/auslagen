from datetime import date, datetime
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from claims.dates import waiver_is_late
from claims.models import DonationChoice, ReportStatus
from claims.tests.factories import german_standard_rate, make_car_line, make_person, make_receipt, make_report
from masterdata.constants import Country, ExpenseType
from masterdata.models import OrganizationSettings
from people.models import MemberType


def test_three_calendar_months_is_the_waiver_limit():
    assert waiver_is_late(date(2026, 1, 15), date(2026, 4, 15)) is False
    assert waiver_is_late(date(2026, 1, 15), date(2026, 4, 16)) is True
    assert waiver_is_late(date(2026, 1, 31), date(2026, 4, 30)) is False
    assert waiver_is_late(date(2026, 1, 31), date(2026, 5, 1)) is True


@pytest.mark.django_db
def test_payout_and_donation_are_separate_amounts(seeded):
    person = make_person()
    report = make_report(person)
    make_car_line(report, gross=Decimal("80.00"))
    make_car_line(report, gross=Decimal("20.00"))
    assert report.gross_total == Decimal("100.00")
    assert report.payout_amount == Decimal("100.00")
    assert report.donation_amount == Decimal("0.00")

    report.donation_choice = DonationChoice.PARTIAL
    report.waiver_amount = Decimal("40.00")
    assert report.donation_amount == Decimal("40.00")
    assert report.payout_amount == Decimal("60.00")

    report.donation_choice = DonationChoice.FULL
    assert report.donation_amount == Decimal("100.00")
    assert report.payout_amount == Decimal("0.00")


@pytest.mark.django_db
def test_complete_payout_has_no_submission_errors(seeded):
    person = make_person()
    report = make_report(person)
    make_car_line(report)
    assert report.submission_errors() == []


@pytest.mark.django_db
def test_missing_donation_choice_is_rejected(seeded):
    person = make_person()
    report = make_report(person, donation_choice="")
    make_car_line(report)
    assert "Die Spendenwahl fehlt. Es gibt keine Vorauswahl." in report.submission_errors()


@pytest.mark.django_db
def test_waiver_stays_hidden_without_a_resolution(seeded):
    person = make_person(
        street="Bergweg 1",
        postal_code="83022",
        city="Rosenheim",
        address_country="DE",
    )
    report = make_report(
        person,
        donation_choice=DonationChoice.FULL,
        waiver_confirmed=True,
        waiver_at=timezone.make_aware(datetime(2026, 6, 2, 10, 0)),
    )
    make_car_line(report)
    assert "Die Spendenoption ist für diese Person nicht freigeschaltet." in report.submission_errors()


@pytest.mark.django_db
def test_partial_waiver_with_resolution_splits_the_money(seeded):
    settings = OrganizationSettings.load()
    settings.reimbursement_resolution_date = date(2020, 1, 15)
    settings.reimbursement_resolution_reference = "Vorstandsbeschluss vom 15.01.2020"
    settings.save()
    person = make_person(
        street="Bergweg 1",
        postal_code="83022",
        city="Rosenheim",
        address_country="DE",
    )
    report = make_report(
        person,
        donation_choice=DonationChoice.PARTIAL,
        waiver_amount=Decimal("15.00"),
        waiver_confirmed=True,
        waiver_at=timezone.make_aware(datetime(2026, 6, 2, 10, 0)),
    )
    receipt = make_receipt(report)
    make_car_line(
        report,
        expense_type=ExpenseType.HOSPITALITY,
        gross=Decimal("48.00"),
        origin="",
        destination="",
        kilometers=None,
        purpose="Gespräch mit dem Wegeigner",
        receipt=receipt,
        receipt_country=Country.DE,
        tax_rate=german_standard_rate(),
        attendee_count=4,
        attendees="Wegeigner und zwei Begeher",
    )
    assert report.submission_errors() == []
    assert report.payout_amount == Decimal("33.00")
    assert report.waiver_warnings() == []


@pytest.mark.django_db
def test_employees_cannot_waive_until_the_setting_is_on(seeded):
    settings = OrganizationSettings.load()
    settings.reimbursement_resolution_date = date(2020, 1, 15)
    settings.reimbursement_resolution_reference = "Vorstandsbeschluss vom 15.01.2020"
    settings.save()
    person = make_person(
        email="angestellt@example.org",
        member_type=MemberType.EMPLOYEE,
        street="Bergweg 1",
        postal_code="83022",
        city="Rosenheim",
        address_country="DE",
    )
    report = make_report(
        person,
        donation_choice=DonationChoice.FULL,
        waiver_confirmed=True,
        waiver_at=timezone.make_aware(datetime(2026, 6, 2, 10, 0)),
    )
    make_car_line(report)
    assert "Die Spendenoption ist für diese Person nicht freigeschaltet." in report.submission_errors()

    settings.donations_enabled_for_employees = True
    settings.save()
    assert report.submission_errors() == []


@pytest.mark.django_db
def test_old_expense_warns_but_still_submits(seeded):
    settings = OrganizationSettings.load()
    settings.reimbursement_resolution_date = date(2020, 1, 15)
    settings.reimbursement_resolution_reference = "Vorstandsbeschluss vom 15.01.2020"
    settings.save()
    person = make_person(
        street="Bergweg 1",
        postal_code="83022",
        city="Rosenheim",
        address_country="DE",
    )
    report = make_report(
        person,
        donation_choice=DonationChoice.FULL,
        waiver_confirmed=True,
        waiver_at=timezone.make_aware(datetime(2026, 6, 1, 10, 0)),
    )
    make_car_line(report, expense_date=date(2026, 1, 1))
    assert report.submission_errors() == []
    assert report.waiver_warnings() == [
        "Zwischen dem ältesten Auslagedatum und der Verzichtserklärung liegen mehr als drei Monate."
    ]


@pytest.mark.django_db
def test_waiver_is_blocked_after_payout(seeded):
    person = make_person()
    report = make_report(person, status=ReportStatus.PAID)
    report.donation_choice = DonationChoice.FULL
    with pytest.raises(ValidationError):
        report.full_clean()
