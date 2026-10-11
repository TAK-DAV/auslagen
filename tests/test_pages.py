import pytest

from people.models import Person


def test_home_page(client):
    response = client.get("/")
    assert response.status_code == 200
    body = response.content.decode()
    assert "Auslagen" in body
    assert "Verwaltungsbereich öffnen" in body


@pytest.mark.django_db
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
