from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from claims.models import DonationChoice, ExpenseReport, ReportStatus
from masterdata.constants import Area, Country, ExpenseType
from masterdata.models import CostCenter, Hut, TaxRate
from people.magic_link import create_login_token
from people.models import Person
from people.roles import SUBMITTER


@pytest.fixture
def submitter(db):
    person = Person.objects.create_user(
        "einreicher@example.org",
        password="unused",
        first_name="Eva",
        last_name="Berg",
    )
    from django.utils import timezone

    person.privacy_acknowledged_at = timezone.now()
    person.iban = "DE89370400440532013000"
    person.save()
    Group.objects.get_or_create(name=SUBMITTER)
    person.groups.add(Group.objects.get(name=SUBMITTER))
    return person


@pytest.mark.django_db
def test_magic_link_request_sends_email(client, submitter, settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    response = client.post(
        reverse("portal:login_request"),
        {"email": submitter.email},
    )
    assert response.status_code == 200
    assert len(mail.outbox) == 1
    assert submitter.email in mail.outbox[0].to


@pytest.mark.django_db
def test_magic_link_login_and_privacy_flow(client, submitter):
    submitter.privacy_acknowledged_at = None
    submitter.save(update_fields=["privacy_acknowledged_at"])
    raw = create_login_token(submitter)
    response = client.get(reverse("portal:magic_login", args=[raw]))
    assert response.status_code == 302
    assert response.url.endswith("/einreichen/datenschutz/")

    response = client.post(
        reverse("portal:privacy"),
        {"accept": "on"},
        follow=True,
    )
    assert response.status_code == 200
    submitter.refresh_from_db()
    assert submitter.privacy_acknowledged_at is not None


@pytest.mark.django_db
def test_submit_report_changes_status(client, submitter, seeded):
    from django.utils import timezone

    submitter.privacy_acknowledged_at = timezone.now()
    submitter.save()
    client.force_login(submitter)
    report = ExpenseReport.objects.create(submitter=submitter, status=ReportStatus.DRAFT)
    de19 = TaxRate.objects.get(country=Country.DE, rate_percent=Decimal("19.00"))
    from claims.models import LineItem, Receipt

    receipt = Receipt.objects.create(
        report=report,
        file=SimpleUploadedFile("b.jpg", b"x", content_type="image/jpeg"),
    )
    LineItem.objects.create(
        report=report,
        expense_type=ExpenseType.HUT_MATERIAL,
        expense_date=date(2026, 6, 1),
        cost_center=CostCenter.objects.get(name="Rotwandhaus Betrieb"),
        hut=Hut.objects.get(name="Rotwandhaus"),
        area=Area.OPERATION,
        usage="Test",
        receipt=receipt,
        receipt_country=Country.DE,
        tax_rate=de19,
        gross=Decimal("119.00"),
    )
    url = reverse("portal:report_submit", args=[report.pk])
    response = client.post(
        url,
        {
            "donation_choice": DonationChoice.PAYOUT,
        },
        follow=True,
    )
    assert response.status_code == 200
    report.refresh_from_db()
    assert report.status == ReportStatus.SUBMITTED
    assert report.submitted_at is not None


@pytest.mark.django_db
def test_cannot_open_other_users_report(client, submitter, seeded):
    from django.utils import timezone

    submitter.privacy_acknowledged_at = timezone.now()
    submitter.save()
    other = Person.objects.create_user("other@example.org", password="x")
    report = ExpenseReport.objects.create(submitter=other, status=ReportStatus.DRAFT)
    client.force_login(submitter)
    response = client.get(reverse("portal:report_detail", args=[report.pk]))
    assert response.status_code == 404
