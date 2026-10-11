from decimal import Decimal

from django.db import models


class EuroField(models.DecimalField):
    """Euro amount stored with two decimal places. Never a float."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("max_digits", 12)
        kwargs.setdefault("decimal_places", 2)
        super().__init__(*args, **kwargs)


def euros(value) -> Decimal:
    """Quantize to cents with commercial rounding (ROUND_HALF_UP)."""
    from decimal import ROUND_HALF_UP

    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def format_eur(amount: Decimal | None) -> str:
    if amount is None:
        return "—"
    quantized = euros(amount)
    sign = "-" if quantized < 0 else ""
    whole, cents = f"{abs(quantized):.2f}".split(".")
    groups = []
    while whole:
        groups.append(whole[-3:])
        whole = whole[:-3]
    return f"{sign}{'.'.join(reversed(groups))},{cents} €"
