from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from claims.tests.factories import german_standard_rate, make_car_line, make_person, make_receipt, make_report
from masterdata.constants import Area, Country, ExpenseType, SphereCode, VatResult
from masterdata.models import CostCenter, Hut, Sphere


@pytest.mark.django_db
def test_line_stores_calendar_year_and_club_year(seeded):
    person = make_person()
    report = make_report(person)
    april = make_car_line(report, expense_date=date(2026, 4, 30))
    may = make_car_line(
        report,
        expense_date=date(2026, 5, 1),
        document_number=None,
    )
    assert april.calendar_year == 2026
    assert april.club_year_start == 2025
    assert april.club_year_label() == "2025/2026"
    assert may.club_year_start == 2026
    assert may.club_year_label() == "2026/2027"


@pytest.mark.django_db
def test_car_line_has_no_vat_and_copies_the_default_sphere(seeded):
    person = make_person()
    report = make_report(person)
    rate = german_standard_rate()
    line = make_car_line(report, tax_rate=rate, receipt_country=Country.DE)
    line.refresh_from_db()
    assert line.vat_result == VatResult.NONE
    assert line.tax_rate_id is None
    assert line.sphere.code == SphereCode.NON_PROFIT
    assert line.net == line.gross
    assert line.tax_amount == Decimal("0.00")


@pytest.mark.django_db
def test_other_expense_starts_as_needs_review(seeded):
    person = make_person()
    report = make_report(person)
    line = make_car_line(
        report,
        expense_type=ExpenseType.OTHER,
        description="Ersatzteil",
        origin="",
        destination="",
        kilometers=None,
        purpose="",
    )
    assert line.vat_result == VatResult.REVIEW


@pytest.mark.django_db
def test_transit_on_verwaltung_has_no_input_vat(seeded):
    person = make_person()
    report = make_report(person)
    receipt = make_receipt(report)
    line = make_car_line(
        report,
        expense_type=ExpenseType.TRANSIT,
        purpose="Bahn zur Hütte",
        origin="",
        destination="",
        kilometers=None,
        receipt_country=Country.DE,
        tax_rate=german_standard_rate(),
        receipt=receipt,
        gross=Decimal("19.00"),
    )
    assert line.vat_result == VatResult.NONE
    assert line.net == Decimal("15.97")
    assert line.tax_amount == Decimal("3.03")


@pytest.mark.django_db
def test_submitter_cannot_approve_own_line(seeded):
    person = make_person()
    report = make_report(person)
    line = make_car_line(report, factual_reviewed_by=person)
    with pytest.raises(ValidationError) as caught:
        line.full_clean()
    assert "factual_reviewed_by" in caught.value.error_dict


@pytest.mark.django_db
def test_sphere_override_needs_a_reason(seeded):
    person = make_person()
    report = make_report(person)
    line = make_car_line(report)
    line.sphere = Sphere.objects.get(code=SphereCode.COMMERCIAL)
    with pytest.raises(ValidationError) as caught:
        line.full_clean()
    assert "sphere_override_reason" in caught.value.error_dict
    line.sphere_override_reason = "Kontenrahmen weicht für diesen Fall ab."
    line.full_clean()


@pytest.mark.django_db
def test_hut_and_area_must_match_the_cost_center(seeded):
    person = make_person()
    report = make_report(person)
    line = make_car_line(
        report,
        expense_type=ExpenseType.HUT_MATERIAL,
        hut=Hut.objects.get(name="Rotwandhaus"),
        area=Area.OPERATION,
        usage="Farbe Fassade",
        cost_center=CostCenter.objects.get(name="Verwaltung / Vorstand"),
    )
    with pytest.raises(ValidationError) as caught:
        line.full_clean()
    assert "cost_center" in caught.value.error_dict

    line.cost_center = CostCenter.objects.get(name="Rotwandhaus Betrieb")
    line.vat_result = ""
    line.full_clean()


@pytest.mark.django_db
def test_tax_rate_must_match_the_receipt_country(seeded):
    person = make_person()
    report = make_report(person)
    line = make_car_line(
        report,
        expense_type=ExpenseType.TRANSIT,
        receipt_country=Country.AT,
        tax_rate=german_standard_rate(),
    )
    with pytest.raises(ValidationError) as caught:
        line.full_clean()
    assert "tax_rate" in caught.value.error_dict


@pytest.mark.django_db
def test_receipt_checksum_and_rejected_extension(seeded):
    import hashlib

    person = make_person()
    report = make_report(person)
    receipt = make_receipt(report, content=b"photo-from-the-hut")
    assert receipt.checksum_sha256 == hashlib.sha256(b"photo-from-the-hut").hexdigest()
    assert receipt.original_name == "bon.jpg"

    bad = make_receipt(report, name="notes.txt", content=b"nope")
    with pytest.raises(ValidationError):
        bad.full_clean()


@pytest.mark.django_db
def test_car_submission_does_not_ask_for_a_receipt(seeded):
    person = make_person()
    report = make_report(person)
    line = make_car_line(report)
    assert line.submission_errors() == []

    line.purpose = ""
    assert "Anlass fehlt." in line.submission_errors()


@pytest.mark.django_db
def test_hospitality_without_guests_is_blocked(seeded):
    person = make_person()
    report = make_report(person)
    receipt = make_receipt(report)
    line = make_car_line(
        report,
        expense_type=ExpenseType.HOSPITALITY,
        purpose="Gespräch mit der Gemeinde",
        origin="",
        destination="",
        kilometers=None,
        receipt=receipt,
        receipt_country=Country.DE,
        tax_rate=german_standard_rate(),
        gross=Decimal("48.00"),
        attendee_count=None,
        attendees="",
    )
    errors = line.submission_errors()
    assert "Teilnehmerzahl fehlt." in errors
    assert "Teilnehmer oder Personenkreis fehlen." in errors
