from decimal import Decimal, ROUND_HALF_UP

CENT = Decimal("0.01")


def to_money(value) -> Decimal:
    """All monetary values are Decimal, rounded half-up to cents. Never use float for money."""
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def apply_discount(amount: Decimal, percent: Decimal) -> Decimal:
    if not Decimal("0") <= percent <= Decimal("100"):
        raise ValueError("discount percent must be between 0 and 100")
    return to_money(amount * (Decimal("100") - percent) / Decimal("100"))
