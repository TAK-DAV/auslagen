from datetime import date
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile

from claims.models import DonationChoice, ExpenseReport, LineItem, Receipt
from masterdata.constants import Country, ExpenseType
from masterdata.models import CostCenter, TaxRate
from people.models import Person


def make_person(email="eva.berg@example.org", **extra):
    password = extra.pop("password", "secret-pass-1")
    extra.setdefault("first_name", "Eva")
    extra.setdefault("last_name", "Berg")
    return Person.objects.create_user(email, password, **extra)


def make_report(submitter, **extra):
    extra.setdefault("donation_choice", DonationChoice.PAYOUT)
    return ExpenseReport.objects.create(submitter=submitter, **extra)


def make_receipt(report, name="bon.jpg", content=b"receipt-bytes"):
    upload = SimpleUploadedFile(name, content, content_type="image/jpeg")
    return Receipt.objects.create(report=report, file=upload)


def make_car_line(report, **extra):
    extra.setdefault("cost_center", CostCenter.objects.get(name="Verwaltung / Vorstand"))
    extra.setdefault("expense_type", ExpenseType.CAR)
    extra.setdefault("expense_date", date(2026, 6, 1))
    extra.setdefault("gross", Decimal("12.00"))
    extra.setdefault("origin", "München")
    extra.setdefault("destination", "Rotwandhaus")
    extra.setdefault("kilometers", Decimal("40.0"))
    extra.setdefault("purpose", "Materialtransport")
    return LineItem.objects.create(report=report, **extra)


def german_standard_rate():
    return TaxRate.objects.get(country=Country.DE, rate_percent=Decimal("19.00"))
