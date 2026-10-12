from decimal import Decimal

from django import forms
from django.db.models import Q

from claims.models import DonationChoice, ExpenseReport, LineItem, ReportStatus
from masterdata.constants import Area, Country, ExpenseType
from masterdata.models import CostCenter, Hut, OrganizationSettings, TaxRate
from people.iban import validate_iban
from people.models import MemberType, Person


class LoginRequestForm(forms.Form):
    email = forms.EmailField(label="E-Mail-Adresse", widget=forms.EmailInput(attrs={"autocomplete": "email"}))


class StaffLoginForm(forms.Form):
    email = forms.EmailField(label="E-Mail")
    password = forms.CharField(label="Passwort", widget=forms.PasswordInput)


class PrivacyForm(forms.Form):
    accept = forms.BooleanField(
        label="Ich habe den Datenschutzhinweis gelesen und zur Kenntnis genommen.",
        required=True,
    )


class ProfileForm(forms.ModelForm):
    class Meta:
        model = Person
        fields = ("first_name", "last_name", "iban", "street", "postal_code", "city", "address_country")
        labels = {
            "first_name": "Vorname",
            "last_name": "Nachname",
            "iban": "IBAN für die Überweisung",
            "street": "Straße und Hausnummer",
            "postal_code": "Postleitzahl",
            "city": "Ort",
            "address_country": "Land (DE oder AT)",
        }

    def clean_iban(self):
        value = self.cleaned_data.get("iban") or ""
        if value:
            validate_iban(value)
        return value


class SubmitReportForm(forms.Form):
    donation_choice = forms.ChoiceField(
        label="Erstattung oder Verzicht",
        choices=DonationChoice.choices,
        widget=forms.RadioSelect,
    )
    waiver_amount = forms.DecimalField(
        label="Verzichtsbetrag in Euro",
        required=False,
        min_value=Decimal("0.01"),
        decimal_places=2,
        max_digits=12,
    )
    waiver_confirmed = forms.BooleanField(
        label="Ich verzichte hiermit auf den Erstattungsanspruch in der gewählten Höhe.",
        required=False,
    )

    def __init__(self, *args, report: ExpenseReport, **kwargs):
        self.report = report
        super().__init__(*args, **kwargs)
        settings = OrganizationSettings.load()
        if not settings.donations_allowed_for(report.submitter):
            self.fields["donation_choice"].choices = [
                (DonationChoice.PAYOUT, DonationChoice.PAYOUT.label),
            ]

    def clean(self):
        cleaned = super().clean()
        choice = cleaned.get("donation_choice")
        if choice in {DonationChoice.PARTIAL, DonationChoice.FULL}:
            if not cleaned.get("waiver_confirmed"):
                self.add_error("waiver_confirmed", "Bitte die Verzichtserklärung bestätigen.")
        if choice == DonationChoice.PARTIAL and not cleaned.get("waiver_amount"):
            self.add_error("waiver_amount", "Beim Teilverzicht fehlt der Betrag.")
        return cleaned


class LineItemForm(forms.ModelForm):
    receipt_file = forms.FileField(
        label="Beleg (Foto oder PDF)",
        required=False,
        widget=forms.FileInput(attrs={"accept": "image/*,.pdf", "capture": "environment"}),
    )

    class Meta:
        model = LineItem
        fields = (
            "expense_type",
            "expense_date",
            "cost_center",
            "gross",
            "receipt_country",
            "tax_rate",
            "purpose",
            "description",
            "origin",
            "destination",
            "kilometers",
            "attendee_count",
            "attendees",
            "hut",
            "area",
            "usage",
            "location",
        )
        widgets = {
            "expense_date": forms.DateInput(attrs={"type": "date"}),
            "description": forms.Textarea(attrs={"rows": 2}),
            "attendees": forms.Textarea(attrs={"rows": 2}),
            "purpose": forms.TextInput(),
        }

    def __init__(self, *args, report: ExpenseReport, **kwargs):
        self.report = report
        super().__init__(*args, **kwargs)
        self.fields["cost_center"].queryset = CostCenter.objects.order_by("list_order", "name")
        self.fields["hut"].queryset = Hut.objects.order_by("name")
        self.fields["tax_rate"].queryset = TaxRate.objects.none()
        self.fields["tax_rate"].required = False
        self.fields["receipt_country"].choices = [("", "—")] + list(Country.choices)
        country = self.data.get("receipt_country") or self.initial.get("receipt_country") or ""
        expense_date = self.data.get("expense_date") or self.initial.get("expense_date")
        if country:
            self.fields["tax_rate"].queryset = _tax_rates_for_country(country, expense_date)
        self.fields["expense_type"].widget.attrs["data-line-type"] = "1"

    def clean_gross(self):
        value = self.cleaned_data["gross"]
        if value is not None and value < 0:
            raise forms.ValidationError("Der Betrag darf nicht negativ sein.")
        return value

    def clean(self):
        cleaned = super().clean()
        expense_type = cleaned.get("expense_type")
        if expense_type == ExpenseType.CAR:
            cleaned["receipt_country"] = ""
            cleaned["tax_rate"] = None
            if not cleaned.get("receipt_file") and not self.instance.receipt_id:
                pass  # no receipt required
        elif expense_type != ExpenseType.CAR:
            if not cleaned.get("receipt_file") and not self.instance.receipt_id:
                self.add_error("receipt_file", "Bitte einen Beleg hochladen.")
        hut = cleaned.get("hut")
        area = cleaned.get("area") or ""
        if expense_type == ExpenseType.HUT_MATERIAL and hut and area:
            match = CostCenter.objects.filter(hut=hut, area=area).first()
            if match:
                cleaned["cost_center"] = match
        return cleaned

    def save(self, commit=True):
        line = super().save(commit=False)
        line.report = self.report
        if commit:
            line.save()
            upload = self.cleaned_data.get("receipt_file")
            if upload:
                from claims.models import Receipt

                receipt = Receipt.objects.create(report=self.report, file=upload)
                line.receipt = receipt
                line.save(update_fields=["receipt"])
        return line


def _tax_rates_for_country(country: str, expense_date):
    qs = TaxRate.objects.filter(country=country)
    if expense_date:
        qs = qs.filter(valid_from__lte=expense_date).filter(
            Q(valid_to__isnull=True) | Q(valid_to__gte=expense_date)
        )
    return qs.order_by("-rate_percent")
