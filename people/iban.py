"""IBAN check digit (ISO 13616). No external dependency."""

import re

from django.core.exceptions import ValidationError

_IBAN_PATTERN = re.compile(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}")


def normalize_iban(value: str) -> str:
    return re.sub(r"\s+", "", value or "").upper()


def validate_iban(value: str) -> None:
    iban = normalize_iban(value)
    if not iban:
        return
    if not _IBAN_PATTERN.fullmatch(iban):
        raise ValidationError("IBAN hat ein ungültiges Format.", code="invalid")
    rearranged = iban[4:] + iban[:4]
    digits = []
    for char in rearranged:
        if char.isdigit():
            digits.append(char)
        else:
            digits.append(str(ord(char) - 55))
    if int("".join(digits)) % 97 != 1:
        raise ValidationError("IBAN-Prüfsumme ist ungültig.", code="invalid")
