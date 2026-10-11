import pytest
from django.core.exceptions import ValidationError

from people.iban import normalize_iban, validate_iban

VALID_DE = "DE89370400440532013000"
VALID_AT = "AT611904300234573201"


def test_normalize_strips_spaces_and_uppercases():
    assert normalize_iban("de89 3704 0044 0532 0130 00") == VALID_DE


def test_valid_german_and_austrian_ibans():
    validate_iban(VALID_DE)
    validate_iban(VALID_AT)


def test_bad_checksum_is_rejected():
    with pytest.raises(ValidationError):
        validate_iban("DE00370400440532013000")


def test_short_value_is_rejected():
    with pytest.raises(ValidationError):
        validate_iban("DE89")


def test_empty_value_is_allowed():
    validate_iban("")
    validate_iban("   ")
