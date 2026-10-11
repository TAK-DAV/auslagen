from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError

from masterdata.constants import Area, Country, SphereCode, VatMode
from masterdata.models import CostCenter, Hut, MileageRate, OrganizationSettings, Sphere, TaxRate
from masterdata.seed import NOTE_FAHRWEG, NOTE_SPHERE_OPEN, seed_masterdata
from people.roles import ROLE_NAMES


@pytest.mark.django_db
def test_seed_creates_the_example_cost_centers():
    seed_masterdata()
    names = list(CostCenter.objects.order_by("list_order").values_list("name", flat=True))
    assert names == [
        "Verwaltung / Vorstand",
        "Ausbildung",
        "Touren",
        "Skiabteilung",
        "Rotwandhaus Betrieb",
        "Rotwandhaus Fahrweg",
        "Rotwandhaus Wanderwege",
        "Babenstuber Hütte Betrieb",
        "Babenstuber Hütte Wanderwege",
        "Gruttenhütte Betrieb",
        "Gruttenhütte Wanderwege",
    ]


@pytest.mark.django_db
def test_open_spheres_stay_empty_and_known_ones_are_set():
    seed_masterdata()
    assert CostCenter.objects.get(name="Ausbildung").default_sphere is None
    assert CostCenter.objects.get(name="Touren").default_sphere is None
    assert CostCenter.objects.get(name="Rotwandhaus Betrieb").default_sphere is None
    assert CostCenter.objects.get(name="Rotwandhaus Fahrweg").default_sphere is None
    assert CostCenter.objects.get(name="Babenstuber Hütte Betrieb").default_sphere is None
    assert CostCenter.objects.get(name="Gruttenhütte Betrieb").default_sphere is None

    ideell = Sphere.objects.get(code=SphereCode.NON_PROFIT)
    for name in (
        "Verwaltung / Vorstand",
        "Skiabteilung",
        "Rotwandhaus Wanderwege",
        "Babenstuber Hütte Wanderwege",
        "Gruttenhütte Wanderwege",
    ):
        assert CostCenter.objects.get(name=name).default_sphere == ideell

    assert CostCenter.objects.get(name="Ausbildung").review_note == NOTE_SPHERE_OPEN
    assert CostCenter.objects.get(name="Rotwandhaus Fahrweg").review_note == NOTE_FAHRWEG


@pytest.mark.django_db
def test_vat_modes_follow_the_country_of_the_hut_operation():
    seed_masterdata()
    assert CostCenter.objects.get(name="Rotwandhaus Betrieb").vat_mode == VatMode.DE
    assert CostCenter.objects.get(name="Rotwandhaus Betrieb").country == Country.DE
    assert CostCenter.objects.get(name="Babenstuber Hütte Betrieb").vat_mode == VatMode.AT
    assert CostCenter.objects.get(name="Gruttenhütte Betrieb").country == Country.AT
    for name in CostCenter.objects.filter(area=Area.TRAILS):
        assert name.vat_mode == VatMode.NONE
        assert name.default_sphere.code == SphereCode.NON_PROFIT


@pytest.mark.django_db
def test_tax_rates_mileage_roles_and_limits():
    seed_masterdata()
    assert TaxRate.objects.count() == 7
    assert set(TaxRate.objects.filter(country=Country.DE).values_list("rate_percent", flat=True)) == {
        Decimal("19.00"),
        Decimal("7.00"),
        Decimal("0.00"),
    }
    assert set(TaxRate.objects.filter(country=Country.AT).values_list("rate_percent", flat=True)) == {
        Decimal("20.00"),
        Decimal("13.00"),
        Decimal("10.00"),
        Decimal("0.00"),
    }
    rate = MileageRate.objects.get()
    assert rate.rate_eur == Decimal("0.30")
    assert rate.valid_from == date(2024, 1, 1)
    settings = OrganizationSettings.load()
    assert settings.small_invoice_limit_de == Decimal("250.00")
    assert settings.small_invoice_limit_at == Decimal("400.00")
    assert settings.donations_enabled_for_employees is False
    assert settings.reimbursement_resolution_date is None
    assert set(Group.objects.values_list("name", flat=True)) == set(ROLE_NAMES)
    assert Hut.objects.count() == 3
    assert Sphere.objects.count() == 4


@pytest.mark.django_db
def test_seed_is_idempotent_and_does_not_overwrite_edits():
    seed_masterdata()
    center = CostCenter.objects.get(name="Verwaltung / Vorstand")
    commercial = Sphere.objects.get(code=SphereCode.COMMERCIAL)
    center.default_sphere = commercial
    center.review_note = "vom Schatzmeister gesetzt"
    center.save()
    seed_masterdata()
    center.refresh_from_db()
    assert center.default_sphere == commercial
    assert center.review_note == "vom Schatzmeister gesetzt"
    assert CostCenter.objects.count() == 11
    assert OrganizationSettings.objects.count() == 1


@pytest.mark.django_db
def test_trails_cannot_carry_input_vat(seeded):
    center = CostCenter.objects.get(name="Rotwandhaus Wanderwege")
    center.vat_mode = VatMode.DE
    with pytest.raises(ValidationError) as caught:
        center.full_clean()
    assert "vat_mode" in caught.value.error_dict


@pytest.mark.django_db
def test_trails_stay_in_the_non_profit_sphere(seeded):
    center = CostCenter.objects.get(name="Gruttenhütte Wanderwege")
    center.default_sphere = Sphere.objects.get(code=SphereCode.COMMERCIAL)
    with pytest.raises(ValidationError) as caught:
        center.full_clean()
    assert "default_sphere" in caught.value.error_dict


@pytest.mark.django_db
def test_cost_center_country_must_match_the_hut(seeded):
    center = CostCenter(
        name="Falsche Zuordnung",
        country=Country.DE,
        vat_mode=VatMode.NONE,
        hut=Hut.objects.get(name="Gruttenhütte"),
        area=Area.OPERATION,
        filing_folder="Test",
    )
    with pytest.raises(ValidationError) as caught:
        center.full_clean()
    assert "country" in caught.value.error_dict
