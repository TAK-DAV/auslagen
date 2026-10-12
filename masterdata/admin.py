from django.contrib import admin

from masterdata.models import (
    Account,
    AccountMapping,
    CostCenter,
    ExportProfile,
    Hut,
    MileageRate,
    OrganizationSettings,
    SolvencyConfirmation,
    Sphere,
    TaxRate,
)


@admin.register(Sphere)
class SphereAdmin(admin.ModelAdmin):
    list_display = ("name", "code")
    search_fields = ("name", "code")


@admin.register(Hut)
class HutAdmin(admin.ModelAdmin):
    list_display = ("name", "country")
    list_filter = ("country",)
    search_fields = ("name",)


@admin.register(CostCenter)
class CostCenterAdmin(admin.ModelAdmin):
    list_display = ("name", "country", "default_sphere", "vat_mode", "area", "review_note")
    list_filter = ("country", "vat_mode", "area")
    search_fields = ("name", "filing_folder", "review_note")
    filter_horizontal = ("approvers",)
    autocomplete_fields = ("default_sphere", "hut")
    fieldsets = (
        (None, {"fields": ("name", "list_order", "country", "filing_folder")}),
        ("Steuer und Sphäre", {"fields": ("default_sphere", "vat_mode", "review_note")}),
        (
            "Hütte",
            {
                "fields": ("hut", "area"),
                "description": "Der Einreicher wählt später nur Hütte und Bereich. Daraus folgt diese Kostenstelle.",
            },
        ),
        (
            "Freigabe",
            {
                "fields": ("approvers",),
                "description": "Wer je Kostenstelle sachlich freigibt und wer vertritt, ist noch offen.",
            },
        ),
    )


@admin.register(TaxRate)
class TaxRateAdmin(admin.ModelAdmin):
    list_display = ("country", "rate_percent", "valid_from", "valid_to")
    list_filter = ("country",)
    search_fields = ("country",)


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ("number", "name", "is_active")
    list_filter = ("is_active",)
    search_fields = ("number", "name")


@admin.register(AccountMapping)
class AccountMappingAdmin(admin.ModelAdmin):
    list_display = ("cost_center", "expense_type", "account")
    list_filter = ("expense_type",)
    autocomplete_fields = ("cost_center", "account")


@admin.register(MileageRate)
class MileageRateAdmin(admin.ModelAdmin):
    list_display = ("rate_eur", "member_type", "role_label", "purpose", "valid_from", "valid_to")


@admin.register(OrganizationSettings)
class OrganizationSettingsAdmin(admin.ModelAdmin):
    autocomplete_fields = (
        "donation_income_account",
        "creditor_account",
        "vat_account_de",
        "vat_account_at",
    )
    fieldsets = (
        ("Verein", {"fields": ("club_name", "club_street", "club_postal_code", "club_city")}),
        ("Bank", {"fields": ("bank_account_holder", "bank_iban", "bank_bic")}),
        (
            "Aufwandsersatz und Spende",
            {
                "fields": (
                    "reimbursement_resolution_date",
                    "reimbursement_resolution_reference",
                    "donations_enabled_for_employees",
                    "donation_income_account",
                ),
                "description": "Ohne Beschlussdatum und Fundstelle gibt es keine Spendenoption.",
            },
        ),
        (
            "Steuer und Konten",
            {
                "fields": (
                    "small_invoice_limit_de",
                    "small_invoice_limit_at",
                    "creditor_account",
                    "vat_account_de",
                    "vat_account_at",
                ),
                "description": "Sachkonten kommen aus dem bestehenden Kontenrahmen. Es ist noch keiner hinterlegt.",
            },
        ),
        (
            "Freistellungsbescheid",
            {"fields": ("exemption_notice_date", "exemption_tax_office", "exemption_reference")},
        ),
        (
            "Zuwendungsbestätigung",
            {
                "fields": ("donation_confirmation_template",),
                "description": "Leer lassen für die Standardvorlage. Amtlichen Text vor dem Echtbetrieb prüfen.",
            },
        ),
    )

    def has_add_permission(self, request):
        return not OrganizationSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ExportProfile)
class ExportProfileAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "is_active")
    search_fields = ("name", "code")


@admin.register(SolvencyConfirmation)
class SolvencyConfirmationAdmin(admin.ModelAdmin):
    list_display = ("calendar_year", "confirmed_on", "confirmed_by")
    autocomplete_fields = ("confirmed_by",)
