import pytest
from django.core.exceptions import ValidationError

from people.models import Person

VALID_DE = "DE89370400440532013000"


@pytest.mark.django_db
def test_iban_is_stored_without_spaces():
    person = Person(email="Eva.Berg@Example.org", iban="de89 3704 0044 0532 0130 00")
    person.set_password("secret-pass-1")
    person.save()
    person.refresh_from_db()
    assert person.email == "eva.berg@example.org"
    assert person.iban == VALID_DE


@pytest.mark.django_db
def test_invalid_iban_cannot_be_saved():
    person = Person(email="eva.berg@example.org", first_name="Eva", last_name="Berg")
    person.set_password("secret-pass-1")
    person.iban = "DE00370400440532013000"
    with pytest.raises(ValidationError):
        person.save()


@pytest.mark.django_db
def test_postal_address_needs_every_part():
    person = Person.objects.create_user(
        "eva.berg@example.org",
        "secret-pass-1",
        street="Bergweg 1",
        postal_code="83022",
        city="Rosenheim",
    )
    assert person.has_postal_address is False
    person.address_country = "DE"
    person.save()
    assert person.has_postal_address is True
