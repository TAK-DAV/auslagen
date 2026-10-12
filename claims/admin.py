from django.contrib import admin

from claims.models import (
    AuditLog,
    DonationConfirmation,
    ExpenseReport,
    LineItem,
    PaymentRun,
    Receipt,
    ReportComment,
)
from tak.fields import format_eur


class LineItemInline(admin.TabularInline):
    model = LineItem
    extra = 0
    show_change_link = True
    autocomplete_fields = ("cost_center", "tax_rate", "sphere", "account", "hut", "factual_reviewed_by")
    readonly_fields = ("net", "tax_amount", "requires_full_invoice")
    fields = (
        "expense_type",
        "expense_date",
        "cost_center",
        "gross",
        "net",
        "tax_amount",
        "receipt_country",
        "tax_rate",
        "vat_result",
        "requires_full_invoice",
        "factual_review",
    )


class ReceiptInline(admin.TabularInline):
    model = Receipt
    extra = 0
    readonly_fields = ("original_name", "checksum_sha256", "uploaded_at")


class ReportCommentInline(admin.TabularInline):
    model = ReportComment
    extra = 0
    autocomplete_fields = ("author",)


@admin.register(ExpenseReport)
class ExpenseReportAdmin(admin.ModelAdmin):
    list_display = ("id", "submitter", "status", "donation_choice", "payout_display", "created_at")
    list_filter = ("status", "donation_choice")
    search_fields = ("submitter__email", "submitter__first_name", "submitter__last_name")
    autocomplete_fields = ("submitter", "payment_run")
    readonly_fields = (
        "gross_total_display",
        "donation_amount_display",
        "payout_display",
        "created_at",
        "updated_at",
    )
    inlines = [LineItemInline, ReceiptInline, ReportCommentInline]
    save_on_top = True
    fieldsets = (
        (None, {"fields": ("submitter", "status", "submitted_at")}),
        (
            "Spende",
            {
                "fields": ("donation_choice", "waiver_amount", "waiver_confirmed", "waiver_at"),
                "description": "Volle Auszahlung, Teilverzicht oder Vollverzicht. Keine Vorauswahl.",
            },
        ),
        (
            "Beträge",
            {"fields": ("gross_total_display", "donation_amount_display", "payout_display")},
        ),
        ("Zahlung", {"fields": ("payment_run",)}),
        ("Zeitpunkte", {"fields": ("created_at", "updated_at")}),
    )

    @admin.display(description="Summe brutto")
    def gross_total_display(self, obj):
        if obj is None or obj.pk is None:
            return "—"
        return format_eur(obj.gross_total)

    @admin.display(description="Davon Verzicht")
    def donation_amount_display(self, obj):
        if obj is None or obj.pk is None:
            return "—"
        return format_eur(obj.donation_amount)

    @admin.display(description="Auszahlung")
    def payout_display(self, obj):
        if obj is None or obj.pk is None:
            return "—"
        return format_eur(obj.payout_amount)


@admin.register(LineItem)
class LineItemAdmin(admin.ModelAdmin):
    list_display = (
        "expense_date",
        "expense_type",
        "cost_center",
        "gross_display",
        "net_display",
        "tax_display",
        "vat_result",
        "requires_full_invoice",
        "factual_review",
        "club_year_display",
    )
    list_filter = (
        "expense_type",
        "vat_result",
        "requires_full_invoice",
        "factual_review",
        "receipt_country",
        "calendar_year",
    )
    search_fields = ("purpose", "description", "document_number", "report__submitter__last_name")
    autocomplete_fields = (
        "report",
        "cost_center",
        "tax_rate",
        "sphere",
        "account",
        "receipt",
        "hut",
        "factual_reviewed_by",
    )
    readonly_fields = ("calendar_year", "club_year_display", "net", "tax_amount", "requires_full_invoice")
    fieldsets = (
        (None, {"fields": ("report", "expense_type", "expense_date", "cost_center", "gross")}),
        (
            "Steuer",
            {
                "fields": (
                    "receipt_country",
                    "tax_rate",
                    "net",
                    "tax_amount",
                    "vat_result",
                    "vat_decision_reason",
                    "requires_full_invoice",
                    "sphere",
                    "sphere_override_reason",
                    "account",
                ),
                "description": (
                    "Netto und Steuer rechnet das System. "
                    "Vorsteuer DE und AT bleiben in Auswertungen getrennt."
                ),
            },
        ),
        ("Beleg", {"fields": ("receipt", "document_number")}),
        (
            "Angaben zur Art",
            {
                "fields": (
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
            },
        ),
        ("Jahre", {"fields": ("calendar_year", "club_year_display")}),
        (
            "Sachliche Prüfung",
            {
                "fields": (
                    "factual_review",
                    "factual_reviewed_by",
                    "factual_reviewed_at",
                    "factual_review_note",
                ),
                "description": "Gilt für diese Position. Der Einreicher kann sie nicht selbst freigeben.",
            },
        ),
    )

    @admin.display(description="Brutto", ordering="gross")
    def gross_display(self, obj):
        return format_eur(obj.gross)

    @admin.display(description="Netto", ordering="net")
    def net_display(self, obj):
        return format_eur(obj.net)

    @admin.display(description="Steuer", ordering="tax_amount")
    def tax_display(self, obj):
        return format_eur(obj.tax_amount)

    @admin.display(description="Vereinsjahr")
    def club_year_display(self, obj):
        if obj is None:
            return "—"
        return obj.club_year_label()


@admin.register(Receipt)
class ReceiptAdmin(admin.ModelAdmin):
    list_display = ("original_name", "report", "checksum_sha256", "uploaded_at")
    search_fields = ("original_name", "checksum_sha256")
    readonly_fields = ("original_name", "checksum_sha256", "uploaded_at")
    autocomplete_fields = ("report",)


@admin.register(PaymentRun)
class PaymentRunAdmin(admin.ModelAdmin):
    list_display = ("id", "created_at", "created_by", "marked_paid_at")
    autocomplete_fields = ("created_by",)
    search_fields = ("note", "created_by__email")


@admin.register(DonationConfirmation)
class DonationConfirmationAdmin(admin.ModelAdmin):
    list_display = ("person", "calendar_year", "total_amount", "issued_at", "created_at")
    autocomplete_fields = ("person",)
    search_fields = ("person__email", "person__last_name")
    readonly_fields = ("total_amount", "issued_at", "body_text", "pdf", "created_at")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "actor", "content_type", "object_id", "field_name")
    list_filter = ("content_type",)
    search_fields = ("field_name", "reason", "old_value", "new_value")
    readonly_fields = (
        "created_at",
        "actor",
        "content_type",
        "object_id",
        "field_name",
        "old_value",
        "new_value",
        "reason",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
