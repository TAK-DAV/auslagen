"""VAT and sphere rules for one expense line.

Money: never float. Tax is rounded per line (ROUND_HALF_UP), then
net = gross − tax so that net + tax always equals gross.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from masterdata.constants import Area, Country, ExpenseType, SphereCode, VatMode, VatResult
from tak.fields import euros

HUNDRED = Decimal("100")
ZERO = Decimal("0.00")


@dataclass(frozen=True)
class MoneySplit:
    gross: Decimal
    net: Decimal
    tax: Decimal

    def __post_init__(self):
        if self.net + self.tax != self.gross:
            raise ValueError("net + tax must equal gross")


@dataclass(frozen=True)
class VatTotals:
    """Input VAT amounts kept apart for the DE and AT returns."""

    de: Decimal
    at: Decimal
    none: Decimal
    review: Decimal

    @property
    def deductible(self) -> Decimal:
        return euros(self.de + self.at)


@dataclass(frozen=True)
class LineTaxResult:
    net: Decimal | None
    tax_amount: Decimal | None
    vat_result: str
    requires_full_invoice: bool
    sphere_code: str | None
    notes: tuple[str, ...] = ()


def rate_as_fraction(rate_percent: Decimal) -> Decimal:
    return Decimal(rate_percent) / HUNDRED


def split_gross(gross: Decimal, rate_percent: Decimal) -> MoneySplit:
    """tax = gross − gross / (1 + rate), commercial rounding; net = gross − tax."""
    gross = euros(gross)
    rate = rate_as_fraction(rate_percent)
    if rate < 0:
        raise ValueError("Tax rate must not be negative.")
    if rate == 0:
        return MoneySplit(gross=gross, net=gross, tax=ZERO)
    tax = euros(gross - (gross / (1 + rate)))
    net = euros(gross - tax)
    return MoneySplit(gross=gross, net=net, tax=tax)


def resolve_vat_result(
    *,
    expense_type: str,
    cost_center_vat_mode: str,
    cost_center_country: str,
    receipt_country: str,
) -> str:
    """Automatic input-VAT outcome for one line.

    Order is fixed:
    1. Car travel → no VAT.
    2. Other → always needs the treasurer (PRUEFEN).
    3. Cost center without deduction → none.
    4. Matching DE / AT → that country's input VAT.
    5. Receipt country ≠ cost-center country → PRUEFEN.
    """
    if expense_type == ExpenseType.CAR:
        return VatResult.NONE
    if expense_type == ExpenseType.OTHER:
        return VatResult.REVIEW
    if cost_center_vat_mode == VatMode.NONE:
        return VatResult.NONE
    if not receipt_country:
        return VatResult.REVIEW
    if cost_center_vat_mode == VatMode.DE and receipt_country == Country.DE:
        return VatResult.DE
    if cost_center_vat_mode == VatMode.AT and receipt_country == Country.AT:
        return VatResult.AT
    if receipt_country != cost_center_country:
        # FACHLICH OFFEN: DE purchase for an AT hut (and the reverse) needs a
        # tax-advisor ruling before the tool may book it automatically.
        return VatResult.REVIEW
    return VatResult.REVIEW


def small_invoice_limit_for(country: str, *, limit_de: Decimal, limit_at: Decimal) -> Decimal | None:
    if country == Country.DE:
        return euros(limit_de)
    if country == Country.AT:
        return euros(limit_at)
    return None


def exceeds_small_invoice_limit(
    gross: Decimal,
    country: str,
    *,
    limit_de: Decimal,
    limit_at: Decimal,
) -> bool:
    """True when the treasurer should expect a full invoice, not a Kleinbetragsrechnung."""
    if country not in {Country.DE, Country.AT}:
        return False
    limit = small_invoice_limit_for(country, limit_de=limit_de, limit_at=limit_at)
    return euros(gross) > limit


def resolve_sphere_code(
    *,
    area: str,
    cost_center_sphere_code: str | None,
    cost_center_area: str = "",
) -> str | None:
    """Default sphere for a line. Hiking trails stay in the non-profit sphere."""
    if area == Area.TRAILS or cost_center_area == Area.TRAILS:
        return SphereCode.NON_PROFIT
    return cost_center_sphere_code or None


def vat_decision_needs_reason(*, automatic_result: str, stored_result: str) -> bool:
    """Treasurer must document the choice when leaving an automatic PRUEFEN."""
    if automatic_result != VatResult.REVIEW:
        return False
    if not stored_result or stored_result == VatResult.REVIEW:
        return False
    return True


def compute_line_tax(
    *,
    expense_type: str,
    gross: Decimal,
    rate_percent: Decimal | None,
    cost_center_vat_mode: str,
    cost_center_country: str,
    receipt_country: str,
    area: str = "",
    cost_center_area: str = "",
    cost_center_sphere_code: str | None = None,
    limit_de: Decimal = Decimal("250.00"),
    limit_at: Decimal = Decimal("400.00"),
) -> LineTaxResult:
    notes: list[str] = []
    vat_result = resolve_vat_result(
        expense_type=expense_type,
        cost_center_vat_mode=cost_center_vat_mode,
        cost_center_country=cost_center_country,
        receipt_country=receipt_country,
    )
    sphere_code = resolve_sphere_code(
        area=area,
        cost_center_sphere_code=cost_center_sphere_code,
        cost_center_area=cost_center_area,
    )

    if expense_type == ExpenseType.CAR:
        split = split_gross(gross, ZERO)
        return LineTaxResult(
            net=split.net,
            tax_amount=split.tax,
            vat_result=VatResult.NONE,
            requires_full_invoice=False,
            sphere_code=sphere_code,
            notes=tuple(notes),
        )

    country_for_limit = receipt_country or cost_center_country
    requires_full = exceeds_small_invoice_limit(
        gross,
        country_for_limit,
        limit_de=limit_de,
        limit_at=limit_at,
    )
    if requires_full:
        notes.append(
            "Über der Kleinbetragsgrenze: der Schatzmeister braucht eine vollständige Rechnung."
        )

    if rate_percent is None:
        return LineTaxResult(
            net=None,
            tax_amount=None,
            vat_result=vat_result,
            requires_full_invoice=requires_full,
            sphere_code=sphere_code,
            notes=tuple(notes),
        )

    split = split_gross(gross, rate_percent)
    if vat_result == VatResult.REVIEW and receipt_country and receipt_country != cost_center_country:
        notes.append(
            "Belegland und Kostenstellenland passen nicht. Vorsteuer erst nach Entscheidung des Schatzmeisters."
        )
    if expense_type == ExpenseType.OTHER:
        notes.append("Sonstiges: Kontierung und Vorsteuer prüft der Schatzmeister.")

    return LineTaxResult(
        net=split.net,
        tax_amount=split.tax,
        vat_result=vat_result,
        requires_full_invoice=requires_full,
        sphere_code=sphere_code,
        notes=tuple(notes),
    )


def sum_vat(lines: Iterable) -> VatTotals:
    """Sum tax amounts by input-VAT bucket. Lines still on PRUEFEN are listed separately."""
    de = ZERO
    at = ZERO
    none = ZERO
    review = ZERO
    for line in lines:
        amount = euros(getattr(line, "tax_amount", None) or ZERO)
        result = getattr(line, "vat_result", "") or ""
        if result == VatResult.DE:
            de = euros(de + amount)
        elif result == VatResult.AT:
            at = euros(at + amount)
        elif result == VatResult.REVIEW:
            review = euros(review + amount)
        else:
            none = euros(none + amount)
    return VatTotals(de=de, at=at, none=none, review=review)


def apply_to_line(line, *, settings=None, preserve_vat_decision: bool = True) -> list[str]:
    """Write net, tax, VAT result and default sphere onto a LineItem. Returns notes."""
    from masterdata.models import OrganizationSettings, Sphere

    if settings is None:
        settings = OrganizationSettings.load()

    cost_center = line.cost_center
    rate_percent = None
    if line.tax_rate_id:
        rate_percent = line.tax_rate.rate_percent

    automatic = compute_line_tax(
        expense_type=line.expense_type,
        gross=line.gross,
        rate_percent=rate_percent,
        cost_center_vat_mode=cost_center.vat_mode,
        cost_center_country=cost_center.country,
        receipt_country=line.receipt_country or "",
        area=line.area or "",
        cost_center_area=cost_center.area or "",
        cost_center_sphere_code=(
            cost_center.default_sphere.code if cost_center.default_sphere_id else None
        ),
        limit_de=settings.small_invoice_limit_de,
        limit_at=settings.small_invoice_limit_at,
    )

    if line.expense_type == ExpenseType.CAR:
        line.tax_rate = None

    line.net = automatic.net
    line.tax_amount = automatic.tax_amount
    line.requires_full_invoice = automatic.requires_full_invoice

    treasurer_decided = (
        preserve_vat_decision
        and line.vat_result
        and line.vat_result != automatic.vat_result
        and (line.vat_decision_reason or "").strip()
    )
    if treasurer_decided:
        # Keep the treasurer's choice; still refresh money and the full-invoice flag.
        pass
    else:
        line.vat_result = automatic.vat_result

    if automatic.sphere_code and line.sphere_id is None:
        line.sphere = Sphere.objects.filter(code=automatic.sphere_code).first()
    elif (
        automatic.sphere_code
        and line.sphere_id
        and getattr(line.sphere, "code", None) != automatic.sphere_code
        and (line.area == Area.TRAILS or cost_center.area == Area.TRAILS)
        and not (line.sphere_override_reason or "").strip()
    ):
        # Trails may not leave the non-profit sphere without a reason — force default.
        line.sphere = Sphere.objects.filter(code=SphereCode.NON_PROFIT).first()

    return list(automatic.notes)
