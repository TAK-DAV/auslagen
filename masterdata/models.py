from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from masterdata.constants import Area, Country, ExpenseType, SphereCode, VatMode
from people.iban import normalize_iban, validate_iban
from people.models import MemberType
from tak.fields import EuroField


class Sphere(models.Model):
    code = models.CharField("Kürzel", max_length=40, unique=True)
    name = models.CharField("Name", max_length=200)

    class Meta:
        verbose_name = "Sphäre"
        verbose_name_plural = "Sphären"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Hut(models.Model):
    name = models.CharField("Name", max_length=200, unique=True)
    country = models.CharField("Land", max_length=2, choices=Country.choices)

    class Meta:
        verbose_name = "Hütte"
        verbose_name_plural = "Hütten"
        ordering = ["name"]

    def __str__(self):
        return self.name


class CostCenter(models.Model):
    name = models.CharField("Name", max_length=200, unique=True)
    list_order = models.PositiveIntegerField("Reihenfolge", default=0)
    country = models.CharField("Land", max_length=2, choices=Country.choices)
    default_sphere = models.ForeignKey(
        Sphere,
        verbose_name="Standard-Sphäre",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="cost_centers",
        help_text="Leer lassen, solange die Sphäre fachlich nicht feststeht.",
    )
    vat_mode = models.CharField("Vorsteuer", max_length=10, choices=VatMode.choices)
    hut = models.ForeignKey(
        Hut,
        verbose_name="Hütte",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="cost_centers",
    )
    area = models.CharField("Bereich", max_length=20, choices=Area.choices, blank=True)
    filing_folder = models.CharField(
        "Themenordner",
        max_length=200,
        help_text="Ordner unter 1267-G-Vorstand/81_Rechnungen/<Jahr>/. An den echten OneDrive-Namen anpassen.",
    )
    approvers = models.ManyToManyField(
        "people.Person",
        verbose_name="Freigeber",
        blank=True,
        related_name="approver_cost_centers",
        help_text="Prüfen Positionen dieser Kostenstelle sachlich. Eigene Auslagen gibt niemand frei.",
    )
    review_note = models.CharField(
        "Hinweis zur fachlichen Klärung",
        max_length=255,
        blank=True,
        help_text="Leer, sobald Sphäre und Vorsteuer endgültig feststehen.",
    )

    class Meta:
        verbose_name = "Kostenstelle"
        verbose_name_plural = "Kostenstellen"
        ordering = ["list_order", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["hut", "area"],
                condition=models.Q(hut__isnull=False) & ~models.Q(area=""),
                name="unique_hut_area",
            )
        ]

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        errors = {}
        if bool(self.hut_id) != bool(self.area):
            errors["area"] = "Hütte und Bereich gehören zusammen."
        if self.hut_id and self.country and self.hut.country != self.country:
            errors["country"] = "Das Land der Kostenstelle muss zum Land der Hütte passen."
        if self.area == Area.TRAILS:
            if self.vat_mode != VatMode.NONE:
                errors["vat_mode"] = "Wanderwege haben keinen Vorsteuerabzug."
            sphere_code = self.default_sphere.code if self.default_sphere_id else ""
            if sphere_code != SphereCode.NON_PROFIT:
                errors["default_sphere"] = "Wanderwege liegen im ideellen Bereich."
        if errors:
            raise ValidationError(errors)


class TaxRate(models.Model):
    country = models.CharField("Land", max_length=2, choices=Country.choices)
    rate_percent = models.DecimalField(
        "Satz in Prozent",
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )
    valid_from = models.DateField("Gültig ab")
    valid_to = models.DateField("Gültig bis", null=True, blank=True)

    class Meta:
        verbose_name = "Steuersatz"
        verbose_name_plural = "Steuersätze"
        ordering = ["country", "-rate_percent"]
        constraints = [
            models.UniqueConstraint(
                fields=["country", "rate_percent", "valid_from"],
                name="unique_tax_rate_version",
            )
        ]

    def __str__(self):
        return f"{self.get_country_display()} {self.rate_percent} %"

    def clean(self):
        super().clean()
        if self.valid_to and self.valid_from and self.valid_to < self.valid_from:
            raise ValidationError({"valid_to": "Gültig bis liegt vor Gültig ab."})


class Account(models.Model):
    number = models.CharField("Kontonummer", max_length=20, unique=True)
    name = models.CharField("Name", max_length=200)
    is_active = models.BooleanField("Aktiv", default=True)

    class Meta:
        verbose_name = "Sachkonto"
        verbose_name_plural = "Sachkonten"
        ordering = ["number"]

    def __str__(self):
        return f"{self.number} {self.name}"


class AccountMapping(models.Model):
    cost_center = models.ForeignKey(
        CostCenter,
        verbose_name="Kostenstelle",
        on_delete=models.PROTECT,
        related_name="account_mappings",
    )
    expense_type = models.CharField("Auslagenart", max_length=30, choices=ExpenseType.choices)
    account = models.ForeignKey(
        Account,
        verbose_name="Sachkonto",
        on_delete=models.PROTECT,
        related_name="mappings",
    )

    class Meta:
        verbose_name = "Kontenmapping"
        verbose_name_plural = "Kontenmappings"
        constraints = [
            models.UniqueConstraint(
                fields=["cost_center", "expense_type"],
                name="unique_account_mapping",
            )
        ]

    def __str__(self):
        return f"{self.cost_center} / {self.get_expense_type_display()}"


class MileageRate(models.Model):
    """Euro per kilometre.

    # FACHLICH OFFEN: which rate applies to which role and which purpose.
    The seed only contains the default of 0.30. A rate of 0 is allowed.
    """

    member_type = models.CharField(
        "Art",
        max_length=20,
        choices=MemberType.choices,
        blank=True,
        help_text="Leer bedeutet: gilt für jede Art.",
    )
    role_label = models.CharField(
        "Rolle",
        max_length=100,
        blank=True,
        help_text="Zum Beispiel Tourenführer. Leer bedeutet: jede Rolle.",
    )
    purpose = models.CharField(
        "Anlass",
        max_length=200,
        blank=True,
        help_text="Leer bedeutet: jeder Anlass.",
    )
    rate_eur = models.DecimalField(
        "Satz je Kilometer in Euro",
        max_digits=6,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )
    valid_from = models.DateField("Gültig ab")
    valid_to = models.DateField("Gültig bis", null=True, blank=True)

    class Meta:
        verbose_name = "Kilometer-Satz"
        verbose_name_plural = "Kilometer-Sätze"
        ordering = ["-valid_from", "role_label", "purpose"]

    def __str__(self):
        who = self.role_label or self.get_member_type_display() or "Standard"
        return f"{who}: {self.rate_eur} €/km"


class OrganizationSettings(models.Model):
    """Singleton row edited by the treasurer."""

    club_name = models.CharField(
        "Vereinsname",
        max_length=200,
        blank=True,
        help_text="Arbeitstitel TAK. Für die Zuwendungsbestätigung den vollständigen Namen eintragen.",
    )
    club_street = models.CharField("Straße und Hausnummer", max_length=200, blank=True)
    club_postal_code = models.CharField("Postleitzahl", max_length=20, blank=True)
    club_city = models.CharField("Ort", max_length=100, blank=True)
    bank_account_holder = models.CharField("Kontoinhaber", max_length=200, blank=True)
    bank_iban = models.CharField(
        "IBAN Vereinskonto",
        max_length=42,
        blank=True,
        validators=[validate_iban],
    )
    bank_bic = models.CharField("BIC", max_length=11, blank=True)
    reimbursement_resolution_date = models.DateField(
        "Datum des Beschlusses zum Aufwandsersatz",
        null=True,
        blank=True,
        help_text="Ohne Datum und Fundstelle bleibt die Spendenoption ausgeblendet.",
    )
    reimbursement_resolution_reference = models.CharField(
        "Fundstelle des Beschlusses",
        max_length=255,
        blank=True,
    )
    donations_enabled_for_employees = models.BooleanField(
        "Verzicht für Angestellte erlaubt",
        default=False,
        help_text="Aus, bis Steuerberater oder Lohnbüro den Verzicht von Angestellten freigeben.",
    )
    small_invoice_limit_de = EuroField("Kleinbetragsgrenze Deutschland", default=Decimal("250.00"))
    small_invoice_limit_at = EuroField("Kleinbetragsgrenze Österreich", default=Decimal("400.00"))
    donation_income_account = models.ForeignKey(
        Account,
        verbose_name="Konto Spendenertrag",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    creditor_account = models.ForeignKey(
        Account,
        verbose_name="Gegenkonto",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    vat_account_de = models.ForeignKey(
        Account,
        verbose_name="Vorsteuerkonto Deutschland",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    vat_account_at = models.ForeignKey(
        Account,
        verbose_name="Vorsteuerkonto Österreich",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    exemption_notice_date = models.DateField("Datum Freistellungsbescheid", null=True, blank=True)
    exemption_tax_office = models.CharField("Finanzamt", max_length=200, blank=True)
    exemption_reference = models.CharField("Aktenzeichen Freistellungsbescheid", max_length=200, blank=True)
    donation_confirmation_template = models.TextField(
        "Vorlage Zuwendungsbestätigung",
        blank=True,
        help_text=(
            "Editierbarer Text. Leer = Standardvorlage. "
            "# FACHLICH OFFEN: amtlichen Mustertext vor dem Echtbetrieb eintragen."
        ),
    )

    class Meta:
        verbose_name = "Einstellungen"
        verbose_name_plural = "Einstellungen"

    def __str__(self):
        return "Einstellungen"

    def save(self, *args, **kwargs):
        self.pk = 1
        if self.bank_iban:
            self.bank_iban = normalize_iban(self.bank_iban)
            validate_iban(self.bank_iban)
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Die Einstellungen können nicht gelöscht werden.")

    @classmethod
    def load(cls):
        from masterdata.seed import settings_defaults

        obj, _created = cls.objects.get_or_create(pk=1, defaults=settings_defaults())
        return obj

    def donations_allowed_for(self, person) -> bool:
        if self.reimbursement_resolution_date is None:
            return False
        if not (self.reimbursement_resolution_reference or "").strip():
            return False
        if person.member_type == MemberType.EMPLOYEE and not self.donations_enabled_for_employees:
            return False
        return True


class ExportProfile(models.Model):
    """Named CSV column mapping. Generic first; Webling/Lexware later."""

    code = models.SlugField("Kürzel", unique=True)
    name = models.CharField("Name", max_length=100)
    description = models.TextField("Beschreibung", blank=True)
    is_active = models.BooleanField("Aktiv", default=True)

    class Meta:
        verbose_name = "Exportprofil"
        verbose_name_plural = "Exportprofile"
        ordering = ["name"]

    def __str__(self):
        return self.name


class SolvencyConfirmation(models.Model):
    """The treasurer confirms once per calendar year that the club can pay."""

    calendar_year = models.PositiveIntegerField("Kalenderjahr", unique=True)
    confirmed_on = models.DateField("Bestätigt am")
    confirmed_by = models.ForeignKey(
        "people.Person",
        verbose_name="Bestätigt von",
        on_delete=models.PROTECT,
        related_name="solvency_confirmations",
    )
    note = models.CharField("Notiz", max_length=255, blank=True)

    class Meta:
        verbose_name = "Zahlungsfähigkeitsbestätigung"
        verbose_name_plural = "Zahlungsfähigkeitsbestätigungen"
        ordering = ["-calendar_year"]

    def __str__(self):
        return str(self.calendar_year)
