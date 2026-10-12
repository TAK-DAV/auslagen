"""Pure rules for tax split, input VAT and spheres. No UI involved."""

from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.core.exceptions import ValidationError

from claims.taxation import (
    compute_line_tax,
    exceeds_small_invoice_limit,
    resolve_sphere_code,
    resolve_vat_result,
    split_gross,
    sum_vat,
    vat_decision_needs_reason,
)
from claims.tests.factories import (
    german_standard_rate,
    make_car_line,
    make_person,
    make_receipt,
    make_report,
)
from masterdata.constants import Area, Country, ExpenseType, SphereCode, VatMode, VatResult
from masterdata.models import CostCenter, Hut, TaxRate


# --- Money split -----------------------------------------------------------


@pytest.mark.parametrize(
    ("gross", "rate", "net", "tax"),
    [
        ("119.00", "19.00", "100.00", "19.00"),
        ("107.00", "7.00", "100.00", "7.00"),
        ("100.00", "0.00", "100.00", "0.00"),
        ("120.00", "20.00", "100.00", "20.00"),
        ("110.00", "10.00", "100.00", "10.00"),
        ("113.00", "13.00", "100.00", "13.00"),
        # Commercial rounding: 10.00 at 19% → tax 1.60, net 8.40
        ("10.00", "19.00", "8.40", "1.60"),
        ("0.99", "19.00", "0.83", "0.16"),
        ("1.00", "7.00", "0.93", "0.07"),
    ],
)
def test_split_gross_keeps_net_plus_tax_equal_to_gross(gross, rate, net, tax):
    split = split_gross(Decimal(gross), Decimal(rate))
    assert split.gross == Decimal(gross)
    assert split.net == Decimal(net)
    assert split.tax == Decimal(tax)
    assert split.net + split.tax == split.gross


def test_split_never_uses_binary_float_drift():
    # 29.99 at 19% is a classic float trap; Decimal must stay exact in cents.
    split = split_gross(Decimal("29.99"), Decimal("19.00"))
    assert split.tax == Decimal("4.79")
    assert split.net == Decimal("25.20")
    assert split.net + split.tax == Decimal("29.99")


# --- Input VAT -------------------------------------------------------------


def test_car_travel_never_has_input_vat():
    assert (
        resolve_vat_result(
            expense_type=ExpenseType.CAR,
            cost_center_vat_mode=VatMode.DE,
            cost_center_country=Country.DE,
            receipt_country=Country.DE,
        )
        == VatResult.NONE
    )


def test_other_expense_always_needs_review():
    assert (
        resolve_vat_result(
            expense_type=ExpenseType.OTHER,
            cost_center_vat_mode=VatMode.DE,
            cost_center_country=Country.DE,
            receipt_country=Country.DE,
        )
        == VatResult.REVIEW
    )


def test_cost_center_without_deduction_yields_none():
    assert (
        resolve_vat_result(
            expense_type=ExpenseType.TRANSIT,
            cost_center_vat_mode=VatMode.NONE,
            cost_center_country=Country.DE,
            receipt_country=Country.DE,
        )
        == VatResult.NONE
    )


def test_matching_de_and_at_modes():
    assert (
        resolve_vat_result(
            expense_type=ExpenseType.HUT_MATERIAL,
            cost_center_vat_mode=VatMode.DE,
            cost_center_country=Country.DE,
            receipt_country=Country.DE,
        )
        == VatResult.DE
    )
    assert (
        resolve_vat_result(
            expense_type=ExpenseType.HUT_MATERIAL,
            cost_center_vat_mode=VatMode.AT,
            cost_center_country=Country.AT,
            receipt_country=Country.AT,
        )
        == VatResult.AT
    )


def test_country_mismatch_needs_treasurer():
    # DE purchase booked against an AT hut cost center.
    assert (
        resolve_vat_result(
            expense_type=ExpenseType.HUT_MATERIAL,
            cost_center_vat_mode=VatMode.AT,
            cost_center_country=Country.AT,
            receipt_country=Country.DE,
        )
        == VatResult.REVIEW
    )
    # AT receipt against a DE cost center with DE deduction.
    assert (
        resolve_vat_result(
            expense_type=ExpenseType.TRANSIT,
            cost_center_vat_mode=VatMode.DE,
            cost_center_country=Country.DE,
            receipt_country=Country.AT,
        )
        == VatResult.REVIEW
    )


def test_no_deduction_wins_over_country_mismatch():
    # Trails / ideal sphere: gross is expense, even if the receipt is from another country.
    assert (
        resolve_vat_result(
            expense_type=ExpenseType.HUT_MATERIAL,
            cost_center_vat_mode=VatMode.NONE,
            cost_center_country=Country.AT,
            receipt_country=Country.DE,
        )
        == VatResult.NONE
    )


def test_missing_receipt_country_needs_review_when_deduction_is_possible():
    assert (
        resolve_vat_result(
            expense_type=ExpenseType.TRANSIT,
            cost_center_vat_mode=VatMode.DE,
            cost_center_country=Country.DE,
            receipt_country="",
        )
        == VatResult.REVIEW
    )


# --- Small invoice ---------------------------------------------------------


def test_small_invoice_limits():
    assert exceeds_small_invoice_limit(
        Decimal("250.00"), Country.DE, limit_de=Decimal("250.00"), limit_at=Decimal("400.00")
    ) is False
    assert exceeds_small_invoice_limit(
        Decimal("250.01"), Country.DE, limit_de=Decimal("250.00"), limit_at=Decimal("400.00")
    ) is True
    assert exceeds_small_invoice_limit(
        Decimal("400.00"), Country.AT, limit_de=Decimal("250.00"), limit_at=Decimal("400.00")
    ) is False
    assert exceeds_small_invoice_limit(
        Decimal("400.01"), Country.AT, limit_de=Decimal("250.00"), limit_at=Decimal("400.00")
    ) is True


# --- Sphere ----------------------------------------------------------------


def test_trails_force_non_profit_sphere():
    assert (
        resolve_sphere_code(
            area=Area.TRAILS,
            cost_center_sphere_code=SphereCode.COMMERCIAL,
        )
        == SphereCode.NON_PROFIT
    )
    assert (
        resolve_sphere_code(
            area="",
            cost_center_area=Area.TRAILS,
            cost_center_sphere_code=None,
        )
        == SphereCode.NON_PROFIT
    )


def test_default_sphere_comes_from_the_cost_center():
    assert (
        resolve_sphere_code(
            area=Area.OPERATION,
            cost_center_sphere_code=SphereCode.COMMERCIAL,
        )
        == SphereCode.COMMERCIAL
    )
    assert resolve_sphere_code(area="", cost_center_sphere_code=None) is None


# --- Treasurer decision on PRUEFEN ----------------------------------------


def test_reason_only_when_leaving_automatic_review():
    assert vat_decision_needs_reason(
        automatic_result=VatResult.REVIEW, stored_result=VatResult.DE
    )
    assert not vat_decision_needs_reason(
        automatic_result=VatResult.REVIEW, stored_result=VatResult.REVIEW
    )
    assert not vat_decision_needs_reason(
        automatic_result=VatResult.REVIEW, stored_result=""
    )
    assert not vat_decision_needs_reason(
        automatic_result=VatResult.DE, stored_result=VatResult.NONE
    )


def test_compute_line_tax_bundles_the_rules():
    result = compute_line_tax(
        expense_type=ExpenseType.HUT_MATERIAL,
        gross=Decimal("119.00"),
        rate_percent=Decimal("19.00"),
        cost_center_vat_mode=VatMode.DE,
        cost_center_country=Country.DE,
        receipt_country=Country.DE,
        area=Area.OPERATION,
        cost_center_sphere_code=SphereCode.COMMERCIAL,
    )
    assert result.net == Decimal("100.00")
    assert result.tax_amount == Decimal("19.00")
    assert result.vat_result == VatResult.DE
    assert result.requires_full_invoice is False
    assert result.sphere_code == SphereCode.COMMERCIAL


def test_compute_flags_full_invoice_and_country_mismatch():
    result = compute_line_tax(
        expense_type=ExpenseType.HUT_MATERIAL,
        gross=Decimal("480.00"),
        rate_percent=Decimal("20.00"),
        cost_center_vat_mode=VatMode.AT,
        cost_center_country=Country.AT,
        receipt_country=Country.DE,
        area=Area.OPERATION,
        limit_de=Decimal("250.00"),
        limit_at=Decimal("400.00"),
    )
    assert result.vat_result == VatResult.REVIEW
    assert result.requires_full_invoice is True
    assert any("Kleinbetragsgrenze" in note for note in result.notes)
    assert any("Belegland" in note for note in result.notes)


# --- Totals ----------------------------------------------------------------


def test_vat_totals_keep_de_and_at_apart():
    lines = [
        SimpleNamespace(vat_result=VatResult.DE, tax_amount=Decimal("19.00")),
        SimpleNamespace(vat_result=VatResult.DE, tax_amount=Decimal("1.60")),
        SimpleNamespace(vat_result=VatResult.AT, tax_amount=Decimal("20.00")),
        SimpleNamespace(vat_result=VatResult.NONE, tax_amount=Decimal("7.00")),
        SimpleNamespace(vat_result=VatResult.REVIEW, tax_amount=Decimal("3.00")),
    ]
    totals = sum_vat(lines)
    assert totals.de == Decimal("20.60")
    assert totals.at == Decimal("20.00")
    assert totals.none == Decimal("7.00")
    assert totals.review == Decimal("3.00")
    assert totals.deductible == Decimal("40.60")


# --- Persistence on LineItem ----------------------------------------------


@pytest.mark.django_db
def test_saving_a_de_hut_line_fills_net_tax_and_vat(seeded):
    person = make_person()
    report = make_report(person)
    receipt = make_receipt(report)
    line = make_car_line(
        report,
        expense_type=ExpenseType.HUT_MATERIAL,
        cost_center=CostCenter.objects.get(name="Rotwandhaus Betrieb"),
        hut=Hut.objects.get(name="Rotwandhaus"),
        area=Area.OPERATION,
        usage="Farbe",
        origin="",
        destination="",
        kilometers=None,
        purpose="",
        receipt=receipt,
        receipt_country=Country.DE,
        tax_rate=german_standard_rate(),
        gross=Decimal("119.00"),
    )
    line.refresh_from_db()
    assert line.net == Decimal("100.00")
    assert line.tax_amount == Decimal("19.00")
    assert line.vat_result == VatResult.DE
    assert line.requires_full_invoice is False


@pytest.mark.django_db
def test_saving_an_at_hut_line_uses_at_vat(seeded):
    person = make_person()
    report = make_report(person)
    receipt = make_receipt(report)
    rate = TaxRate.objects.get(country=Country.AT, rate_percent=Decimal("20.00"))
    line = make_car_line(
        report,
        expense_type=ExpenseType.HUT_MATERIAL,
        cost_center=CostCenter.objects.get(name="Gruttenhütte Betrieb"),
        hut=Hut.objects.get(name="Gruttenhütte"),
        area=Area.OPERATION,
        usage="Holz",
        origin="",
        destination="",
        kilometers=None,
        purpose="",
        receipt=receipt,
        receipt_country=Country.AT,
        tax_rate=rate,
        gross=Decimal("120.00"),
    )
    assert line.vat_result == VatResult.AT
    assert line.net == Decimal("100.00")
    assert line.tax_amount == Decimal("20.00")


@pytest.mark.django_db
def test_trails_have_no_input_vat_and_stay_non_profit(seeded):
    person = make_person()
    report = make_report(person)
    receipt = make_receipt(report)
    line = make_car_line(
        report,
        expense_type=ExpenseType.HUT_MATERIAL,
        cost_center=CostCenter.objects.get(name="Rotwandhaus Wanderwege"),
        hut=Hut.objects.get(name="Rotwandhaus"),
        area=Area.TRAILS,
        usage="Wegemarkierung",
        origin="",
        destination="",
        kilometers=None,
        purpose="",
        receipt=receipt,
        receipt_country=Country.DE,
        tax_rate=german_standard_rate(),
        gross=Decimal("119.00"),
    )
    assert line.vat_result == VatResult.NONE
    assert line.tax_amount == Decimal("19.00")
    assert line.sphere.code == SphereCode.NON_PROFIT


@pytest.mark.django_db
def test_car_line_stores_zero_tax(seeded):
    person = make_person()
    report = make_report(person)
    line = make_car_line(report, gross=Decimal("12.00"), tax_rate=german_standard_rate())
    line.refresh_from_db()
    assert line.vat_result == VatResult.NONE
    assert line.tax_rate_id is None
    assert line.net == Decimal("12.00")
    assert line.tax_amount == Decimal("0.00")


@pytest.mark.django_db
def test_verwaltung_has_no_input_vat(seeded):
    person = make_person()
    report = make_report(person)
    receipt = make_receipt(report)
    line = make_car_line(
        report,
        expense_type=ExpenseType.TRANSIT,
        purpose="Bahn",
        origin="",
        destination="",
        kilometers=None,
        receipt=receipt,
        receipt_country=Country.DE,
        tax_rate=TaxRate.objects.get(country=Country.DE, rate_percent=Decimal("7.00")),
        gross=Decimal("10.70"),
    )
    assert line.vat_result == VatResult.NONE
    assert line.net == Decimal("10.00")
    assert line.tax_amount == Decimal("0.70")


@pytest.mark.django_db
def test_country_mismatch_marks_review_and_needs_reason_to_decide(seeded):
    person = make_person()
    report = make_report(person)
    receipt = make_receipt(report)
    line = make_car_line(
        report,
        expense_type=ExpenseType.HUT_MATERIAL,
        cost_center=CostCenter.objects.get(name="Gruttenhütte Betrieb"),
        hut=Hut.objects.get(name="Gruttenhütte"),
        area=Area.OPERATION,
        usage="Material aus Rosenheim",
        origin="",
        destination="",
        kilometers=None,
        purpose="",
        receipt=receipt,
        receipt_country=Country.DE,
        tax_rate=german_standard_rate(),
        gross=Decimal("119.00"),
    )
    assert line.vat_result == VatResult.REVIEW
    assert any("Belegland" in note for note in line.tax_notes())

    line.vat_result = VatResult.NONE
    with pytest.raises(ValidationError) as caught:
        line.full_clean()
    assert "vat_decision_reason" in caught.value.error_dict

    line.vat_decision_reason = "Kein Vorsteuerabzug in AT für diesen DE-Beleg."
    line.full_clean()
    line.save()
    line.refresh_from_db()
    assert line.vat_result == VatResult.NONE
    assert line.net == Decimal("100.00")


@pytest.mark.django_db
def test_amount_over_small_invoice_limit_is_flagged(seeded):
    person = make_person()
    report = make_report(person)
    receipt = make_receipt(report)
    line = make_car_line(
        report,
        expense_type=ExpenseType.HUT_MATERIAL,
        cost_center=CostCenter.objects.get(name="Rotwandhaus Betrieb"),
        hut=Hut.objects.get(name="Rotwandhaus"),
        area=Area.OPERATION,
        usage="Große Lieferung",
        origin="",
        destination="",
        kilometers=None,
        purpose="",
        receipt=receipt,
        receipt_country=Country.DE,
        tax_rate=german_standard_rate(),
        gross=Decimal("250.01"),
    )
    assert line.requires_full_invoice is True
    assert any("Kleinbetragsgrenze" in note for note in line.tax_notes())


@pytest.mark.django_db
def test_report_vat_totals_split_de_and_at(seeded):
    person = make_person()
    report = make_report(person)
    receipt = make_receipt(report)
    make_car_line(
        report,
        expense_type=ExpenseType.HUT_MATERIAL,
        cost_center=CostCenter.objects.get(name="Rotwandhaus Betrieb"),
        hut=Hut.objects.get(name="Rotwandhaus"),
        area=Area.OPERATION,
        usage="Farbe",
        origin="",
        destination="",
        kilometers=None,
        purpose="",
        receipt=receipt,
        receipt_country=Country.DE,
        tax_rate=german_standard_rate(),
        gross=Decimal("119.00"),
    )
    at_rate = TaxRate.objects.get(country=Country.AT, rate_percent=Decimal("20.00"))
    make_car_line(
        report,
        expense_type=ExpenseType.HUT_MATERIAL,
        cost_center=CostCenter.objects.get(name="Babenstuber Hütte Betrieb"),
        hut=Hut.objects.get(name="Babenstuber Hütte"),
        area=Area.OPERATION,
        usage="Gas",
        origin="",
        destination="",
        kilometers=None,
        purpose="",
        receipt=receipt,
        receipt_country=Country.AT,
        tax_rate=at_rate,
        gross=Decimal("120.00"),
    )
    make_car_line(report, gross=Decimal("30.00"))
    totals = report.vat_totals()
    assert totals.de == Decimal("19.00")
    assert totals.at == Decimal("20.00")
    assert totals.none == Decimal("0.00")
    assert totals.deductible == Decimal("39.00")


@pytest.mark.django_db
def test_other_stays_on_review_even_with_matching_countries(seeded):
    person = make_person()
    report = make_report(person)
    receipt = make_receipt(report)
    line = make_car_line(
        report,
        expense_type=ExpenseType.OTHER,
        description="Unklarer Einkauf",
        cost_center=CostCenter.objects.get(name="Rotwandhaus Betrieb"),
        origin="",
        destination="",
        kilometers=None,
        purpose="",
        receipt=receipt,
        receipt_country=Country.DE,
        tax_rate=german_standard_rate(),
        gross=Decimal("11.90"),
    )
    assert line.vat_result == VatResult.REVIEW
    assert line.net == Decimal("10.00")
    assert line.tax_amount == Decimal("1.90")
