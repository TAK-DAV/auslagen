import os
from decimal import Decimal

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from claims.dates import local_date, waiver_is_late
from claims.files import receipt_upload_to, sha256_of_file, validate_receipt_file
from claims.taxation import (
    apply_to_line,
    resolve_vat_result,
    sum_vat,
    vat_decision_needs_reason,
)
from claims.years import club_year_label, club_year_start
from masterdata.constants import Area, Country, ExpenseType, VatResult
from masterdata.models import CostCenter, Hut, TaxRate
from tak.fields import EuroField, euros, format_eur


class ReportStatus(models.TextChoices):
    DRAFT = "ENTWURF", "Entwurf"
    SUBMITTED = "EINGEREICHT", "Eingereicht"
    REVIEWED = "SACHLICH_GEPRUEFT", "Sachlich geprüft"
    APPROVED = "FREIGEGEBEN", "Freigegeben"
    IN_PAYMENT = "IN_ZAHLUNGSLAUF", "Im Zahlungslauf"
    PAID = "AUSGEZAHLT", "Ausgezahlt"
    DONE = "ERLEDIGT", "Erledigt"


class DonationChoice(models.TextChoices):
    PAYOUT = "AUSZAHLUNG", "Volle Auszahlung"
    PARTIAL = "TEILVERZICHT", "Teilverzicht"
    FULL = "VOLLVERZICHT", "Vollverzicht"


class FactualReview(models.TextChoices):
    OPEN = "OFFEN", "Offen"
    APPROVED = "SACHLICH_FREIGEGEBEN", "Sachlich freigegeben"
    QUESTION = "RUECKFRAGE", "Rückfrage"


WAIVER_CHOICES = {DonationChoice.PARTIAL, DonationChoice.FULL}
PAID_STATUSES = {ReportStatus.PAID, ReportStatus.DONE}


class ExpenseReport(models.Model):
    """One submission. Several lines can use different cost centers.

    Factual approval is stored on each line, never as a single yes for the
    whole report. The donation amount and the payout amount are separate.
    Status follows only the money that will be transferred.
    """

    submitter = models.ForeignKey(
        "people.Person",
        verbose_name="Einreicher",
        on_delete=models.PROTECT,
        related_name="expense_reports",
    )
    status = models.CharField(
        "Status",
        max_length=30,
        choices=ReportStatus.choices,
        default=ReportStatus.DRAFT,
    )
    submitted_at = models.DateTimeField("Eingereicht am", null=True, blank=True)
    donation_choice = models.CharField(
        "Spendenwahl",
        max_length=20,
        choices=DonationChoice.choices,
        blank=True,
        help_text="Keine Vorauswahl. Der Einreicher entscheidet beim Einreichen.",
    )
    waiver_amount = EuroField(
        "Verzichtsbetrag",
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Nur beim Teilverzicht, in Euro. Der Rest wird überwiesen.",
    )
    waiver_confirmed = models.BooleanField(
        "Verzicht bestätigt",
        default=False,
        help_text="Checkbox der Verzichtserklärung.",
    )
    waiver_at = models.DateTimeField("Verzicht erklärt am", null=True, blank=True)
    payment_run = models.ForeignKey(
        "PaymentRun",
        verbose_name="Zahlungslauf",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="reports",
    )
    created_at = models.DateTimeField("Angelegt am", auto_now_add=True)
    updated_at = models.DateTimeField("Geändert am", auto_now=True)

    class Meta:
        verbose_name = "Abrechnung"
        verbose_name_plural = "Abrechnungen"
        ordering = ["-created_at"]

    def __str__(self):
        who = self.submitter if self.submitter_id else "ohne Einreicher"
        return f"Abrechnung {self.pk or 'neu'} ({who})"

    def clean(self):
        super().clean()
        if not self.pk:
            return
        previous = ExpenseReport.objects.get(pk=self.pk)
        if previous.status not in PAID_STATUSES:
            return
        donation_changed = (
            previous.donation_choice != self.donation_choice
            or previous.waiver_amount != self.waiver_amount
            or previous.waiver_confirmed != self.waiver_confirmed
        )
        if donation_changed:
            raise ValidationError("Nach der Auszahlung ist ein Verzicht gesperrt.")

    @property
    def gross_total(self) -> Decimal:
        total = sum((line.gross for line in self.lines.all()), Decimal("0.00"))
        return euros(total)

    @property
    def donation_amount(self) -> Decimal:
        if self.donation_choice == DonationChoice.FULL:
            return self.gross_total
        if self.donation_choice == DonationChoice.PARTIAL:
            return euros(self.waiver_amount or Decimal("0.00"))
        return Decimal("0.00")

    @property
    def payout_amount(self) -> Decimal:
        return euros(self.gross_total - self.donation_amount)

    def vat_totals(self):
        """DE and AT input VAT kept separate for the two VAT returns."""
        return sum_vat(self.lines.all())

    def submission_errors(self) -> list[str]:
        from masterdata.models import OrganizationSettings

        errors = []
        lines = list(self.lines.all())
        if not lines:
            errors.append("Mindestens eine Position ist nötig.")
        if self.payout_amount > 0 and not (self.submitter.iban or "").strip():
            errors.append("Im Profil fehlt die IBAN für die Überweisung.")
        if not self.donation_choice:
            errors.append("Die Spendenwahl fehlt. Es gibt keine Vorauswahl.")
        if self.donation_choice in WAIVER_CHOICES:
            settings = OrganizationSettings.load()
            if not settings.donations_allowed_for(self.submitter):
                errors.append("Die Spendenoption ist für diese Person nicht freigeschaltet.")
            if not self.waiver_confirmed or self.waiver_at is None:
                errors.append("Der Verzicht braucht eine bestätigte Erklärung mit Zeitpunkt.")
            if not self.submitter.has_postal_address:
                errors.append("Für eine Spende braucht es die Postanschrift.")
        if self.donation_choice == DonationChoice.PARTIAL:
            if self.waiver_amount is None or self.waiver_amount <= 0:
                errors.append("Beim Teilverzicht fehlt der Betrag in Euro.")
            elif lines and self.waiver_amount >= self.gross_total:
                errors.append("Ein Teilverzicht muss kleiner als die Summe der Positionen sein.")
        if self.donation_choice == DonationChoice.PAYOUT and self.waiver_amount:
            errors.append("Bei voller Auszahlung gibt es keinen Verzichtsbetrag.")
        if (
            self.donation_choice == DonationChoice.FULL
            and self.waiver_amount is not None
            and lines
            and self.waiver_amount != self.gross_total
        ):
            errors.append("Beim Vollverzicht ist der Verzichtsbetrag die ganze Summe.")
        for index, line in enumerate(lines, start=1):
            for line_error in line.submission_errors():
                errors.append(f"Position {index}: {line_error}")
        return errors

    def waiver_warnings(self) -> list[str]:
        # FACHLICH OFFEN: with several lines, the oldest expense date counts.
        if self.donation_choice not in WAIVER_CHOICES or self.waiver_at is None:
            return []
        dates = [line.expense_date for line in self.lines.all() if line.expense_date]
        if not dates:
            return []
        if waiver_is_late(min(dates), local_date(self.waiver_at)):
            return [
                "Zwischen dem ältesten Auslagedatum und der Verzichtserklärung liegen mehr als drei Monate."
            ]
        return []


class Receipt(models.Model):
    """Original file plus checksum. Several lines may share one receipt."""

    report = models.ForeignKey(
        ExpenseReport,
        verbose_name="Abrechnung",
        on_delete=models.PROTECT,
        related_name="receipts",
    )
    file = models.FileField("Datei", upload_to=receipt_upload_to, validators=[validate_receipt_file])
    original_name = models.CharField("Dateiname", max_length=255, blank=True)
    checksum_sha256 = models.CharField("SHA-256", max_length=64, blank=True, editable=False)
    uploaded_at = models.DateTimeField("Hochgeladen am", auto_now_add=True)

    class Meta:
        verbose_name = "Beleg"
        verbose_name_plural = "Belege"
        ordering = ["uploaded_at"]

    def __str__(self):
        return self.original_name or f"Beleg {self.pk}"

    def save(self, *args, **kwargs):
        if self.file:
            self.original_name = os.path.basename(self.file.name)
            self.checksum_sha256 = sha256_of_file(self.file)
        super().save(*args, **kwargs)


class LineItem(models.Model):
    """Smallest booking unit. One receipt can feed several lines (mixed VAT rates).

    # FACHLICH OFFEN: the receipt-number sequence is not defined yet.
    The number sits on the line because each line can post to another account.
    """

    report = models.ForeignKey(
        ExpenseReport,
        verbose_name="Abrechnung",
        on_delete=models.PROTECT,
        related_name="lines",
    )
    expense_type = models.CharField("Auslagenart", max_length=30, choices=ExpenseType.choices)
    expense_date = models.DateField("Datum")
    cost_center = models.ForeignKey(
        CostCenter,
        verbose_name="Kostenstelle",
        on_delete=models.PROTECT,
        related_name="lines",
    )
    receipt_country = models.CharField(
        "Land des Belegs",
        max_length=2,
        choices=Country.choices,
        blank=True,
    )
    tax_rate = models.ForeignKey(
        TaxRate,
        verbose_name="Steuersatz",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="lines",
    )
    gross = EuroField("Bruttobetrag", validators=[MinValueValidator(Decimal("0"))])
    net = EuroField(
        "Netto",
        null=True,
        blank=True,
        help_text="Steuer je Position kaufmännisch auf den Cent, Netto = Brutto minus Steuer.",
        editable=False,
    )
    tax_amount = EuroField("Steuer", null=True, blank=True, editable=False)
    vat_result = models.CharField(
        "Vorsteuer",
        max_length=10,
        choices=VatResult.choices,
        blank=True,
        help_text="Automatisch aus Kostenstelle und Belegland. Sonstiges und Land-Konflikt: Prüfung nötig.",
    )
    vat_decision_reason = models.TextField(
        "Begründung zur Vorsteuer",
        blank=True,
        help_text="Pflicht, wenn aus „Prüfung nötig“ eine andere Vorsteuer wird.",
    )
    requires_full_invoice = models.BooleanField(
        "Vollständige Rechnung nötig",
        default=False,
        help_text="Hinweis: Brutto über der Kleinbetragsgrenze des Beleglands.",
    )
    sphere = models.ForeignKey(
        "masterdata.Sphere",
        verbose_name="Sphäre",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="lines",
        help_text="Standard aus der Kostenstelle. Eine Abweichung braucht eine Begründung.",
    )
    sphere_override_reason = models.TextField("Begründung zur Sphäre", blank=True)
    account = models.ForeignKey(
        "masterdata.Account",
        verbose_name="Sachkonto",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="lines",
    )
    receipt = models.ForeignKey(
        Receipt,
        verbose_name="Beleg",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="lines",
    )
    purpose = models.CharField("Anlass", max_length=255, blank=True)
    description = models.TextField("Beschreibung", blank=True)
    origin = models.CharField("Start", max_length=200, blank=True)
    destination = models.CharField("Ziel", max_length=200, blank=True)
    kilometers = models.DecimalField(
        "Kilometer",
        max_digits=7,
        decimal_places=1,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )
    attendee_count = models.PositiveIntegerField("Teilnehmerzahl", null=True, blank=True)
    attendees = models.TextField("Teilnehmer oder Personenkreis", blank=True)
    hut = models.ForeignKey(
        Hut,
        verbose_name="Hütte",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="lines",
    )
    area = models.CharField("Bereich", max_length=20, choices=Area.choices, blank=True)
    usage = models.CharField("Verwendungszweck", max_length=255, blank=True)
    location = models.CharField("Ort", max_length=200, blank=True)
    calendar_year = models.PositiveIntegerField("Kalenderjahr", null=True, editable=False)
    club_year_start = models.PositiveIntegerField(
        "Vereinsjahr ab",
        null=True,
        editable=False,
        help_text="Jahr des 1. Mai. Das Vereinsjahr läuft vom 1.5. bis zum 30.4.",
    )
    document_number = models.CharField("Belegnummer", max_length=40, null=True, blank=True, unique=True)
    factual_review = models.CharField(
        "Sachliche Prüfung",
        max_length=30,
        choices=FactualReview.choices,
        default=FactualReview.OPEN,
    )
    factual_reviewed_by = models.ForeignKey(
        "people.Person",
        verbose_name="Geprüft von",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="factually_reviewed_lines",
    )
    factual_reviewed_at = models.DateTimeField("Geprüft am", null=True, blank=True)
    factual_review_note = models.TextField("Notiz zur Prüfung", blank=True)

    class Meta:
        verbose_name = "Position"
        verbose_name_plural = "Positionen"
        ordering = ["expense_date", "pk"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(gross__gte=0),
                name="line_gross_non_negative",
            ),
            models.CheckConstraint(
                condition=models.Q(kilometers__isnull=True) | models.Q(kilometers__gte=0),
                name="line_kilometers_non_negative",
            ),
        ]

    def __str__(self):
        return f"{self.get_expense_type_display()} {format_eur(self.gross)}"

    def club_year_label(self) -> str:
        return club_year_label(self.club_year_start)

    def clean(self):
        super().clean()
        errors = {}
        if self.expense_type == ExpenseType.CAR and self.tax_rate_id:
            errors["tax_rate"] = "Eine Pkw-Fahrt hat keine Umsatzsteuer."
        if (
            self.tax_rate_id
            and self.receipt_country
            and self.tax_rate.country != self.receipt_country
        ):
            errors["tax_rate"] = "Der Steuersatz passt nicht zum Land des Belegs."
        if bool(self.hut_id) != bool(self.area):
            errors["area"] = "Hütte und Bereich gehören zusammen."
        if self.hut_id and self.area:
            match = CostCenter.objects.filter(hut_id=self.hut_id, area=self.area).first()
            if match is None:
                errors["area"] = "Für diese Hütte und diesen Bereich gibt es keine Kostenstelle."
            elif self.cost_center_id and match.pk != self.cost_center_id:
                errors["cost_center"] = "Hütte und Bereich passen nicht zur Kostenstelle."
        if self.sphere_id and self.cost_center_id and self.cost_center.default_sphere_id:
            if self.sphere_id != self.cost_center.default_sphere_id and not (
                self.sphere_override_reason or ""
            ).strip():
                errors["sphere_override_reason"] = (
                    "Eine Abweichung von der Standard-Sphäre braucht eine Begründung."
                )
        if self.factual_reviewed_by_id and self.report_id:
            if self.factual_reviewed_by_id == self.report.submitter_id:
                errors["factual_reviewed_by"] = "Eigene Auslagen kann niemand selbst freigeben."
        if self.cost_center_id and self.gross is not None:
            automatic = resolve_vat_result(
                expense_type=self.expense_type,
                cost_center_vat_mode=self.cost_center.vat_mode,
                cost_center_country=self.cost_center.country,
                receipt_country=self.receipt_country or "",
            )
            if vat_decision_needs_reason(
                automatic_result=automatic,
                stored_result=self.vat_result or "",
            ) and not (self.vat_decision_reason or "").strip():
                errors["vat_decision_reason"] = (
                    "Eine Entscheidung bei „Prüfung nötig“ braucht eine Begründung."
                )
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.expense_date:
            self.calendar_year = self.expense_date.year
            self.club_year_start = club_year_start(self.expense_date)
        if self.document_number is not None and not str(self.document_number).strip():
            self.document_number = None
        if self.cost_center_id:
            apply_to_line(self)
        super().save(*args, **kwargs)

    def tax_notes(self) -> list[str]:
        """Hints for the treasurer (small invoice, country mismatch). Not blocking."""
        if not self.cost_center_id or self.gross is None:
            return []
        from masterdata.models import OrganizationSettings

        from claims.taxation import compute_line_tax

        settings = OrganizationSettings.load()
        rate_percent = self.tax_rate.rate_percent if self.tax_rate_id else None
        result = compute_line_tax(
            expense_type=self.expense_type,
            gross=self.gross,
            rate_percent=rate_percent,
            cost_center_vat_mode=self.cost_center.vat_mode,
            cost_center_country=self.cost_center.country,
            receipt_country=self.receipt_country or "",
            area=self.area or "",
            cost_center_area=self.cost_center.area or "",
            cost_center_sphere_code=(
                self.cost_center.default_sphere.code
                if self.cost_center.default_sphere_id
                else None
            ),
            limit_de=settings.small_invoice_limit_de,
            limit_at=settings.small_invoice_limit_at,
        )
        return list(result.notes)

    def submission_errors(self) -> list[str]:
        errors = []
        if self.expense_date is None:
            errors.append("Datum fehlt.")
        if self.cost_center_id is None:
            errors.append("Kostenstelle fehlt.")
        if self.gross is None:
            errors.append("Bruttobetrag fehlt.")
        elif self.gross <= 0 and self.expense_type != ExpenseType.CAR:
            errors.append("Bruttobetrag muss größer als 0 sein.")
        if self.expense_type == ExpenseType.CAR:
            if not self.origin:
                errors.append("Start fehlt.")
            if not self.destination:
                errors.append("Ziel fehlt.")
            if self.kilometers is None or self.kilometers <= 0:
                errors.append("Kilometer fehlen.")
            if not self.purpose:
                errors.append("Anlass fehlt.")
            if self.receipt_id:
                errors.append("Eine Pkw-Fahrt hat keinen Beleg.")
            if self.tax_rate_id:
                errors.append("Eine Pkw-Fahrt hat keine Umsatzsteuer.")
        else:
            if self.receipt_country not in {Country.DE, Country.AT}:
                errors.append("Land des Belegs fehlt.")
            if self.tax_rate_id is None:
                errors.append("Steuersatz fehlt.")
            if self.receipt_id is None:
                errors.append("Beleg fehlt.")
        if self.expense_type in {
            ExpenseType.TRANSIT,
            ExpenseType.HOSPITALITY,
            ExpenseType.CREW_MEALS,
            ExpenseType.LODGING,
        } and not self.purpose:
            errors.append("Anlass fehlt.")
        if self.expense_type == ExpenseType.HOSPITALITY:
            if not self.attendee_count:
                errors.append("Teilnehmerzahl fehlt.")
            if not (self.attendees or "").strip():
                errors.append("Teilnehmer oder Personenkreis fehlen.")
        if self.expense_type == ExpenseType.CREW_MEALS and not self.attendee_count:
            errors.append("Teilnehmerzahl fehlt.")
        if self.expense_type == ExpenseType.HUT_MATERIAL:
            if self.hut_id is None:
                errors.append("Hütte fehlt.")
            if not self.area:
                errors.append("Bereich fehlt.")
            if not (self.usage or "").strip():
                errors.append("Verwendungszweck fehlt.")
        if self.expense_type == ExpenseType.LODGING and not self.location:
            errors.append("Ort fehlt.")
        if self.expense_type == ExpenseType.OTHER and not (self.description or "").strip():
            errors.append("Beschreibung fehlt.")
        return errors


class ReportComment(models.Model):
    report = models.ForeignKey(
        ExpenseReport,
        verbose_name="Abrechnung",
        on_delete=models.PROTECT,
        related_name="comments",
    )
    author = models.ForeignKey(
        "people.Person",
        verbose_name="Autor",
        on_delete=models.PROTECT,
        related_name="report_comments",
    )
    body = models.TextField("Kommentar")
    created_at = models.DateTimeField("Zeitpunkt", auto_now_add=True)

    class Meta:
        verbose_name = "Rückfrage"
        verbose_name_plural = "Rückfragen"
        ordering = ["created_at"]

    def __str__(self):
        if self.created_at is None:
            return str(self.author)
        return f"{self.author} am {self.created_at:%d.%m.%Y}"


class PaymentRun(models.Model):
    """A batch the treasurer uploads at the bank. This tool never pays by itself."""

    created_at = models.DateTimeField("Angelegt am", auto_now_add=True)
    created_by = models.ForeignKey(
        "people.Person",
        verbose_name="Angelegt von",
        on_delete=models.PROTECT,
        related_name="payment_runs",
    )
    note = models.CharField("Notiz", max_length=255, blank=True)
    marked_paid_at = models.DateTimeField(
        "Als überwiesen markiert am",
        null=True,
        blank=True,
        help_text="Nur ein Vermerk, nachdem die Datei im Bankportal liegt.",
    )

    class Meta:
        verbose_name = "Zahlungslauf"
        verbose_name_plural = "Zahlungsläufe"
        ordering = ["-created_at"]

    def __str__(self):
        if self.created_at is None:
            return "Zahlungslauf"
        return f"Zahlungslauf {self.pk} vom {self.created_at:%d.%m.%Y}"


class DonationConfirmation(models.Model):
    """Yearly donation receipt. The official PDF is a later phase."""

    person = models.ForeignKey(
        "people.Person",
        verbose_name="Spender",
        on_delete=models.PROTECT,
        related_name="donation_confirmations",
    )
    calendar_year = models.PositiveIntegerField("Kalenderjahr")
    created_at = models.DateTimeField("Angelegt am", auto_now_add=True)

    class Meta:
        verbose_name = "Zuwendungsbestätigung"
        verbose_name_plural = "Zuwendungsbestätigungen"
        ordering = ["-calendar_year", "person"]
        constraints = [
            models.UniqueConstraint(
                fields=["person", "calendar_year"],
                name="unique_donation_confirmation_year",
            )
        ]

    def __str__(self):
        return f"{self.person} {self.calendar_year}"


class AuditLog(models.Model):
    """Who changed which field, including the previous value and the reason.

    Writing these rows is part of the workflow phase. The table is ready so
    later edits of a submitted report have somewhere to go.
    """

    created_at = models.DateTimeField("Zeitpunkt", auto_now_add=True)
    actor = models.ForeignKey(
        "people.Person",
        verbose_name="Wer",
        null=True,
        on_delete=models.PROTECT,
        related_name="audit_entries",
    )
    content_type = models.ForeignKey(ContentType, on_delete=models.PROTECT, verbose_name="Objektart")
    object_id = models.PositiveBigIntegerField("Objekt")
    content_object = GenericForeignKey("content_type", "object_id")
    field_name = models.CharField("Feld", max_length=100)
    old_value = models.TextField("Alter Wert", blank=True)
    new_value = models.TextField("Neuer Wert", blank=True)
    reason = models.TextField("Grund", blank=True)

    class Meta:
        verbose_name = "Änderungsprotokoll"
        verbose_name_plural = "Änderungsprotokoll"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.field_name} am {self.created_at:%d.%m.%Y %H:%M}"
