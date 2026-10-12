import pytest
from django.conf import settings
from django.test import override_settings

from people.models import Person

ADMIN_TEST_MIDDLEWARE = [
    m for m in settings.MIDDLEWARE if m != "portal.middleware.StaffOTPVerifiedMiddleware"
]


def test_home_page(client):
    response = client.get("/")
    assert response.status_code == 200
    body = response.content.decode()
    assert "Auslagen" in body
    assert "Auslagen einreichen" in body
    assert "Verwaltungsbereich" in body


@pytest.mark.django_db
@override_settings(MIDDLEWARE=ADMIN_TEST_MIDDLEWARE)
def test_admin_shows_seeded_cost_centers(client, seeded):
    person = Person.objects.create_superuser("schatz@example.org", "secret-pass-1")
    client.force_login(person)
    overview = client.get("/admin/")
    assert overview.status_code == 200
    overview_body = overview.content.decode()
    assert "Kostenstellen" in overview_body
    assert "Abrechnungen" in overview_body

    cost_centers = client.get("/admin/masterdata/costcenter/")
    assert cost_centers.status_code == 200
    listing = cost_centers.content.decode()
    assert "Rotwandhaus Wanderwege" in listing
    assert "Babenstuber Hütte Betrieb" in listing
    assert "FACHLICH OFFEN: Sphäre ideell oder Zweckbetrieb festlegen." in listing

    add_person = client.get("/admin/people/person/add/")
    assert add_person.status_code == 200
    assert "E-Mail" in add_person.content.decode()
