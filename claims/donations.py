"""Aufwandsspende: booking split and yearly donation receipts.

# FACHLICH OFFEN: exact wording of the official Zuwendungsbestätigung template
# must be checked with the tax advisor. The PDF is built from an editable
# Django template string stored in OrganizationSettings.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from io import BytesIO

from django.core.files.base import ContentFile
from django.db import transaction
from django.template import Context, Template
from django.utils import timezone

from claims.models import DonationConfirmation, ExpenseReport, ReportStatus, WAIVER_CHOICES
from masterdata.constants import SphereCode
from masterdata.models import OrganizationSettings
from tak.fields import euros

ZERO = Decimal("0.00")


@dataclass(frozen=True)
class DonationBookingLine:
    """One booking row implied by a waiver (in addition to the expense booking)."""

    account_number: str
    contra_account: str
    amount: Decimal
    text: str
    sphere_code: str


def waiver_reports_for_year(calendar_year: int):
    return (
        ExpenseReport.objects.filter(
            donation_choice__in=WAIVER_CHOICES,
            status__in={
                ReportStatus.APPROVED,
                ReportStatus.IN_PAYMENT,
                ReportStatus.PAID,
                ReportStatus.DONE,
            },
            lines__calendar_year=calendar_year,
        )
        .distinct()
        .select_related("submitter")
        .prefetch_related("lines")
    )


def donation_total_for_person(person, calendar_year: int) -> Decimal:
    total = ZERO
    for report in waiver_reports_for_year(calendar_year).filter(submitter=person):
        # Only count lines in that calendar year proportionally by gross share.
        year_gross = sum(
            (line.gross for line in report.lines.all() if line.calendar_year == calendar_year),
            ZERO,
        )
        if year_gross <= 0 or report.gross_total <= 0:
            continue
        share = euros(year_gross / report.gross_total * report.donation_amount)
        total = euros(total + share)
    return total


def donation_booking_lines(report: ExpenseReport) -> list[DonationBookingLine]:
    """Extra credit booking for the waived amount into the ideal sphere."""
    amount = report.donation_amount
    if amount <= 0:
        return []
    settings = OrganizationSettings.load()
    account = settings.donation_income_account
    contra = settings.creditor_account
    if account is None or contra is None:
        return []
    return [
        DonationBookingLine(
            account_number=account.number,
            contra_account=contra.number,
            amount=amount,
            text=f"Aufwandsspende Abrechnung {report.pk}",
            sphere_code=SphereCode.NON_PROFIT,
        )
    ]


DEFAULT_CONFIRMATION_TEMPLATE = """\
Zuwendungsbestätigung über Geldzuwendungen
(Arbeitstext – bitte vor dem Echtbetrieb prüfen lassen)

{{ club_name }}
{{ club_street }}
{{ club_postal_code }} {{ club_city }}

Wir bestätigen, dass
{{ donor_name }}
{{ donor_street }}
{{ donor_postal_code }} {{ donor_city }}

im Kalenderjahr {{ calendar_year }} auf die Erstattung von Aufwendungen
in Höhe von insgesamt {{ total_amount }} Euro verzichtet hat.

Verzicht auf die Erstattung von Aufwendungen: Ja

Freistellungsbescheid: {{ exemption_tax_office }}, {{ exemption_reference }},
Datum {{ exemption_notice_date }}

Beschluss Aufwandsersatz: {{ resolution_reference }} vom {{ resolution_date }}

Anlage – Einzelverzichte:
{% for row in items %}- Abrechnung #{{ row.report_id }} vom {{ row.date }}: {{ row.amount }} €
{% endfor %}
"""


def render_confirmation_text(person, calendar_year: int) -> str:
    settings = OrganizationSettings.load()
    template_source = (settings.donation_confirmation_template or "").strip() or DEFAULT_CONFIRMATION_TEMPLATE
    items = []
    for report in waiver_reports_for_year(calendar_year).filter(submitter=person):
        year_gross = sum(
            (line.gross for line in report.lines.all() if line.calendar_year == calendar_year),
            ZERO,
        )
        if year_gross <= 0 or report.gross_total <= 0:
            continue
        amount = euros(year_gross / report.gross_total * report.donation_amount)
        if amount <= 0:
            continue
        items.append(
            {
                "report_id": report.pk,
                "date": report.submitted_at.date().isoformat() if report.submitted_at else "",
                "amount": f"{amount:.2f}",
            }
        )
    total = donation_total_for_person(person, calendar_year)
    context = {
        "club_name": settings.club_name,
        "club_street": settings.club_street,
        "club_postal_code": settings.club_postal_code,
        "club_city": settings.club_city,
        "donor_name": person.get_full_name() or person.email,
        "donor_street": person.street,
        "donor_postal_code": person.postal_code,
        "donor_city": person.city,
        "calendar_year": calendar_year,
        "total_amount": f"{total:.2f}",
        "exemption_tax_office": settings.exemption_tax_office,
        "exemption_reference": settings.exemption_reference,
        "exemption_notice_date": settings.exemption_notice_date,
        "resolution_reference": settings.reimbursement_resolution_reference,
        "resolution_date": settings.reimbursement_resolution_date,
        "items": items,
    }
    return Template(template_source).render(Context(context))


def build_confirmation_pdf(text: str) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.pdfgen import canvas

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - 2 * cm
    pdf.setFont("Helvetica", 10)
    for line in text.splitlines():
        if y < 2 * cm:
            pdf.showPage()
            pdf.setFont("Helvetica", 10)
            y = height - 2 * cm
        # Helvetica has limited glyphs; keep ASCII-friendly fallbacks for €
        safe = line.replace("€", "EUR").replace("—", "-")
        pdf.drawString(2 * cm, y, safe[:110])
        y -= 14
    pdf.save()
    return buffer.getvalue()


@transaction.atomic
def issue_confirmation(person, calendar_year: int, *, actor=None) -> DonationConfirmation:
    total = donation_total_for_person(person, calendar_year)
    if total <= 0:
        raise ValueError("Keine Verzichte in diesem Jahr für diese Person.")
    if not person.has_postal_address:
        raise ValueError("Postanschrift des Spenders fehlt.")
    settings = OrganizationSettings.load()
    if not settings.donations_allowed_for(person):
        raise ValueError("Spendenoption ist für diese Person nicht freigeschaltet.")

    text = render_confirmation_text(person, calendar_year)
    pdf_bytes = build_confirmation_pdf(text)
    confirmation, _created = DonationConfirmation.objects.get_or_create(
        person=person,
        calendar_year=calendar_year,
    )
    confirmation.total_amount = total
    confirmation.issued_at = timezone.now()
    confirmation.body_text = text
    filename = f"zuwendung_{calendar_year}_{person.pk}.pdf"
    confirmation.pdf.save(filename, ContentFile(pdf_bytes), save=False)
    confirmation.save()
    return confirmation


def people_with_waivers(calendar_year: int):
    from people.models import Person

    ids = waiver_reports_for_year(calendar_year).values_list("submitter_id", flat=True).distinct()
    return Person.objects.filter(pk__in=ids).order_by("last_name", "first_name")
