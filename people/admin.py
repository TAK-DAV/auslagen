from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from django.contrib import admin

from people.models import LoginToken, Person


class PersonChangeForm(UserChangeForm):
    class Meta:
        model = Person
        fields = "__all__"


class PersonCreationForm(UserCreationForm):
    class Meta:
        model = Person
        fields = ("email", "first_name", "last_name", "member_type")


@admin.register(Person)
class PersonAdmin(UserAdmin):
    form = PersonChangeForm
    add_form = PersonCreationForm
    ordering = ("last_name", "first_name")
    list_display = ("email", "first_name", "last_name", "member_type", "is_active")
    list_filter = ("member_type", "is_staff", "is_active", "groups")
    search_fields = ("email", "first_name", "last_name", "city")
    filter_horizontal = ("groups", "user_permissions")
    readonly_fields = ("last_login", "date_joined")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Name", {"fields": ("first_name", "last_name", "member_type")}),
        ("Zahlung", {"fields": ("iban",)}),
        (
            "Anschrift",
            {
                "fields": ("street", "postal_code", "city", "address_country"),
                "description": "Pflicht, sobald diese Person auf eine Erstattung verzichtet.",
            },
        ),
        (
            "Berechtigungen",
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        ("Datenschutz", {"fields": ("privacy_acknowledged_at",)}),
        ("Zeitpunkte", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "first_name",
                    "last_name",
                    "member_type",
                    "password1",
                    "password2",
                ),
            },
        ),
    )


@admin.register(LoginToken)
class LoginTokenAdmin(admin.ModelAdmin):
    list_display = ("user", "created_at", "expires_at", "used_at")
    search_fields = ("user__email",)
    readonly_fields = ("token_hash", "created_at", "expires_at", "used_at")

    def has_add_permission(self, request):
        return False
