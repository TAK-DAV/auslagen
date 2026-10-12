from datetime import date
from decimal import Decimal
from xml.etree import ElementTree as ET

import pytest
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from claims.donations import (
    donation_booking_lines,
    donation_total_for_person,
    issue_confirmation,
    render_confirmation_text,
)
from claims.exports import booking_rows_for_run, csv_booking_list, receipts_zip, sepa_pain001
from claims.models import (
    DonationChoice,
    DonationConfirmation,
    ExpenseReport,
    LineItem,
    Receipt,
    ReportStatus,
)
from claims.payments import create_payment_run, mark_payment_run_paid
from masterdata.constants import Area, Country, ExpenseType
from masterdata.models import Account, CostCenter, Hut, OrganizationSettings, TaxRate
from people.models import Person
from people.roles import TREASURER


@pytest.fixture
def finance_setup(db, seeded):
    settings = OrganizationSettings.load()
    settings.reimbursement_resolution_date = date(2020, 1, 15)
    settings.reimbursement_resolution_reference = "Vorstandsbeschluss 15.01.2020"
    settings.club_name = "Sektion TAK"
    settings.club_street = "Berg 1"
    settings.club_postal_code = "83022"
    settings.club_city = "Rosenheim"
    settings.bank_account_holder = "Sektion TAK"
    settings.bank_iban = "DE89370400440532013000"
    settings.bank_bic = "COBADEFFXXX"
    settings.exemption_tax_office = "FA Rosenheim"
    settings.exemption_reference = "123/456"
    settings.exemption_notice_date = date(2024, 1, 1)
    donation_acc = Account.objects.create(number="3220", name="Spendenertrag")
    creditor = Account.objects.create(number="1700", name="Verbindlichkeiten")
    expense_acc = Account.objects.create(number="4900", name="Sachaufwand")
    settings.donation_income_account = donation_acc
    settings.creditor_account = creditor
    settings.save()

    submitter = Person.objects.create_user(
        "spender@example.org",
        password="x",
        first_name="Eva",
        last_name="Berg",
        iban="DE02120300000000202051",
        street="Weg 2",
        postal_code="80331",
        city="München",
        address_country="DE",
    )
    treasurer = Person.objects.create_user(
        "schatz@example.org",
        password="secret-pass-1",
        is_staff=True,
    )
    Group.objects.get_or_create(name=TREASURER)
    treasurer.groups.add(Group.objects.get(name=TREASURER))

    report = ExpenseReport.objects.create(
        submitter=submitter,
        status=ReportStatus.APPROVED,
        submitted_at=timezone.now(),
        donation_choice=DonationChoice.PARTIAL,
        waiver_amount=Decimal("40.00"),
        waiver_confirmed=True,
        waiver_at=timezone.now(),
    )
    receipt = Receipt.objects.create(
        report=report,
        file=SimpleUploadedFile("bon.jpg", b"photo", content_type="image/jpeg"),
    )
    de19 = TaxRate.objects.get(country=Country.DE, rate_percent=Decimal("19.00"))
    LineItem.objects.create(
        report=report,
        expense_type=ExpenseType.HUT_MATERIAL,
        expense_date=date(2026, 6, 1),
        cost_center=CostCenter.objects.get(name="Rotwandhaus Betrieb"),
        hut=Hut.objects.get(name="Rotwandhaus"),
        area=Area.OPERATION,
        usage="Farbe",
        receipt=receipt,
        receipt_country=Country.DE,
        tax_rate=de19,
        gross=Decimal("119.00"),
        account=expense_acc,
    )
    return {
        "settings": settings,
        "submitter": submitter,
        "treasurer": treasurer,
        "report": report,
        "expense_acc": expense_acc,
    }


@pytest.mark.django_db
def test_donation_booking_and_total(finance_setup):
    report = finance_setup["report"]
    assert report.donation_amount == Decimal("40.00")
    assert report.payout_amount == Decimal("79.00")
    lines = donation_booking_lines(report)
    assert len(lines) == 1
    assert lines[0].amount == Decimal("40.00")
    assert lines[0].account_number == "3220"
    assert donation_total_for_person(finance_setup["submitter"], 2026) == Decimal("40.00")


@pytest.mark.django_db
def test_issue_confirmation_pdf(finance_setup):
    person = finance_setup["submitter"]
    text = render_confirmation_text(person, 2026)
    assert "Verzicht auf die Erstattung von Aufwendungen: Ja" in text
    assert "40.00" in text
    confirmation = issue_confirmation(person, 2026)
    assert confirmation.total_amount == Decimal("40.00")
    assert confirmation.pdf.name.endswith(".pdf")
    assert confirmation.pdf.size > 100
    assert DonationConfirmation.objects.filter(person=person, calendar_year=2026).count() == 1


@pytest.mark.django_db
def test_payment_run_csv_sepa_zip_and_paid(finance_setup):
    # Full payout report for SEPA (reuse same person with a second report)
    submitter = finance_setup["submitter"]
    expense_acc = finance_setup["expense_acc"]
    report2 = ExpenseReport.objects.create(
        submitter=submitter,
        status=ReportStatus.APPROVED,
        submitted_at=timezone.now(),
        donation_choice=DonationChoice.PAYOUT,
    )
    receipt = Receipt.objects.create(
        report=report2,
        file=SimpleUploadedFile("b2.jpg", b"yy", content_type="image/jpeg"),
    )
    de19 = TaxRate.objects.get(country=Country.DE, rate_percent=Decimal("19.00"))
    LineItem.objects.create(
        report=report2,
        expense_type=ExpenseType.HUT_MATERIAL,
        expense_date=date(2026, 6, 2),
        cost_center=CostCenter.objects.get(name="Rotwandhaus Betrieb"),
        hut=Hut.objects.get(name="Rotwandhaus"),
        area=Area.OPERATION,
        usage="Schrauben",
        receipt=receipt,
        receipt_country=Country.DE,
        tax_rate=de19,
        gross=Decimal("23.80"),
        account=expense_acc,
    )

    # Partial waiver report also has payout → include both
    run = create_payment_run(
        finance_setup["treasurer"],
        report_ids=[finance_setup["report"].pk, report2.pk],
    )
    assert run.reports.count() == 2
    finance_setup["report"].refresh_from_db()
    assert finance_setup["report"].status == ReportStatus.IN_PAYMENT

    rows = booking_rows_for_run(run)
    assert any(r.document_number.startswith("S-") for r in rows)
    csv_bytes = csv_booking_list(run)
    assert csv_bytes.startswith(b"\xef\xbb\xbf")
    assert b"Belegnummer" in csv_bytes
    assert b"40,00" in csv_bytes or b"40.00" in csv_bytes

    xml = sepa_pain001(run)
    root = ET.fromstring(xml)
    ns = {"p": "urn:iso:std:iso:20022:tech:xsd:pain.001.001.03"}
    amounts = [el.text for el in root.findall(".//p:InstdAmt", ns)]
    assert "79.00" in amounts
    assert "23.80" in amounts

    zipped = receipts_zip(run)
    assert zipped[:2] == b"PK"

    mark_payment_run_paid(finance_setup["treasurer"], run)
    finance_setup["report"].refresh_from_db()
    report2.refresh_from_db()
    assert finance_setup["report"].status == ReportStatus.PAID
    assert report2.status == ReportStatus.PAID
