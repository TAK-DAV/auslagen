from datetime import date
from decimal import Decimal

from claims.years import club_year_label, club_year_start
from tak.fields import euros, format_eur


def test_club_year_turns_on_1_may():
    assert club_year_start(date(2026, 4, 30)) == 2025
    assert club_year_start(date(2026, 5, 1)) == 2026
    assert club_year_label(2025) == "2025/2026"


def test_commercial_rounding_to_cents():
    assert euros("1.005") == Decimal("1.01")
    assert euros("1.004") == Decimal("1.00")
    assert euros("10.00") == Decimal("10.00")


def test_german_euro_format():
    assert format_eur(Decimal("1234.5")) == "1.234,50 €"
    assert format_eur(Decimal("0")) == "0,00 €"
    assert format_eur(Decimal("-2.5")) == "-2,50 €"
    assert format_eur(None) == "—"
