from decimal import Decimal

from django.contrib.auth.models import Group

from masterdata.constants import Area, Country, SphereCode, VatMode
from people.roles import ROLE_NAMES

# FACHLICH OFFEN: placeholder, not the legal effective date of these rates.
TAX_RATE_VALID_FROM_PLACEHOLDER = "2024-01-01"

# FACHLICH OFFEN: which kilometre rate applies to which role and purpose.
MILEAGE_DEFAULT_EUR = Decimal("0.30")

NOTE_SPHERE_OPEN = "FACHLICH OFFEN: Sphäre ideell oder Zweckbetrieb festlegen."
NOTE_FROM_CHART = "FACHLICH OFFEN: Standard-Sphäre aus dem Kontenrahmen übernehmen."
NOTE_FAHRWEG = "FACHLICH OFFEN: Sphäre unternehmerisch einer der vier Sphären zuordnen."


def settings_defaults():
    return {
        "club_name": "TAK",
        "small_invoice_limit_de": Decimal("250.00"),
        "small_invoice_limit_at": Decimal("400.00"),
        "donations_enabled_for_employees": False,
    }


def seed_masterdata():
    """Create master data if it is missing. Never overwrite later edits."""
    from datetime import date

    from masterdata.models import (
        CostCenter,
        Hut,
        MileageRate,
        OrganizationSettings,
        Sphere,
        TaxRate,
    )

    spheres = {
        SphereCode.NON_PROFIT: "Ideeller Bereich",
        SphereCode.ASSET_MANAGEMENT: "Vermögensverwaltung",
        SphereCode.PURPOSE_BUSINESS: "Zweckbetrieb",
        SphereCode.COMMERCIAL: "Wirtschaftlicher Geschäftsbetrieb",
    }
    for code, name in spheres.items():
        Sphere.objects.get_or_create(code=code, defaults={"name": name})

    valid_from = date.fromisoformat(TAX_RATE_VALID_FROM_PLACEHOLDER)
    for country, rate in (
        (Country.DE, "19.00"),
        (Country.DE, "7.00"),
        (Country.DE, "0.00"),
        (Country.AT, "20.00"),
        (Country.AT, "13.00"),
        (Country.AT, "10.00"),
        (Country.AT, "0.00"),
    ):
        TaxRate.objects.get_or_create(
            country=country,
            rate_percent=Decimal(rate),
            valid_from=valid_from,
        )

    huts = {}
    for name, country in (
        ("Rotwandhaus", Country.DE),
        ("Babenstuber Hütte", Country.AT),
        ("Gruttenhütte", Country.AT),
    ):
        hut, _created = Hut.objects.get_or_create(name=name, defaults={"country": country})
        huts[name] = hut

    ideell = Sphere.objects.get(code=SphereCode.NON_PROFIT)
    # FACHLICH OFFEN: approver per cost center, and who deputises.
    cost_centers = [
        dict(name="Verwaltung / Vorstand", list_order=10, country=Country.DE, sphere=ideell, vat_mode=VatMode.NONE, hut=None, area="", filing_folder="Verwaltung", review_note=""),
        dict(name="Ausbildung", list_order=20, country=Country.DE, sphere=None, vat_mode=VatMode.NONE, hut=None, area="", filing_folder="Ausbildung", review_note=NOTE_SPHERE_OPEN),
        dict(name="Touren", list_order=30, country=Country.DE, sphere=None, vat_mode=VatMode.NONE, hut=None, area="", filing_folder="Touren", review_note=NOTE_SPHERE_OPEN),
        dict(name="Skiabteilung", list_order=40, country=Country.DE, sphere=ideell, vat_mode=VatMode.NONE, hut=None, area="", filing_folder="Skiabteilung", review_note=""),
        dict(name="Rotwandhaus Betrieb", list_order=50, country=Country.DE, sphere=None, vat_mode=VatMode.DE, hut=huts["Rotwandhaus"], area=Area.OPERATION, filing_folder="Rotwandhaus", review_note=NOTE_FROM_CHART),
        dict(name="Rotwandhaus Fahrweg", list_order=60, country=Country.DE, sphere=None, vat_mode=VatMode.DE, hut=huts["Rotwandhaus"], area=Area.ACCESS_ROAD, filing_folder="Rotwandhaus", review_note=NOTE_FAHRWEG),
        dict(name="Rotwandhaus Wanderwege", list_order=70, country=Country.DE, sphere=ideell, vat_mode=VatMode.NONE, hut=huts["Rotwandhaus"], area=Area.TRAILS, filing_folder="Rotwandhaus", review_note=""),
        dict(name="Babenstuber Hütte Betrieb", list_order=80, country=Country.AT, sphere=None, vat_mode=VatMode.AT, hut=huts["Babenstuber Hütte"], area=Area.OPERATION, filing_folder="Babenstuber-Huette", review_note=NOTE_FROM_CHART),
        dict(name="Babenstuber Hütte Wanderwege", list_order=90, country=Country.AT, sphere=ideell, vat_mode=VatMode.NONE, hut=huts["Babenstuber Hütte"], area=Area.TRAILS, filing_folder="Babenstuber-Huette", review_note=""),
        dict(name="Gruttenhütte Betrieb", list_order=100, country=Country.AT, sphere=None, vat_mode=VatMode.AT, hut=huts["Gruttenhütte"], area=Area.OPERATION, filing_folder="Gruttenhuette", review_note=NOTE_FROM_CHART),
        dict(name="Gruttenhütte Wanderwege", list_order=110, country=Country.AT, sphere=ideell, vat_mode=VatMode.NONE, hut=huts["Gruttenhütte"], area=Area.TRAILS, filing_folder="Gruttenhuette", review_note=""),
    ]
    for row in cost_centers:
        CostCenter.objects.get_or_create(
            name=row["name"],
            defaults={
                "list_order": row["list_order"],
                "country": row["country"],
                "default_sphere": row["sphere"],
                "vat_mode": row["vat_mode"],
                "hut": row["hut"],
                "area": row["area"],
                "filing_folder": row["filing_folder"],
                "review_note": row["review_note"],
            },
        )

    MileageRate.objects.get_or_create(
        member_type="",
        role_label="",
        purpose="",
        valid_from=valid_from,
        defaults={"rate_eur": MILEAGE_DEFAULT_EUR},
    )

    OrganizationSettings.objects.get_or_create(pk=1, defaults=settings_defaults())

    for role_name in ROLE_NAMES:
        Group.objects.get_or_create(name=role_name)

    from masterdata.models import ExportProfile

    ExportProfile.objects.get_or_create(
        code="generic",
        defaults={
            "name": "Generische Buchungsliste",
            "description": "CSV mit Semikolon. Später Profile für Webling oder Lexware ergänzen.",
        },
    )
