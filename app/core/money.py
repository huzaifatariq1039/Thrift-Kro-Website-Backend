"""Shared fixed-precision monetary helpers."""

from decimal import Decimal, ROUND_HALF_UP
from typing import Union


MONEY_PRECISION = 14
MONEY_SCALE = 2
MONEY_QUANTUM = Decimal("0.01")
ZERO_MONEY = Decimal("0.00")

MoneyInput = Union[Decimal, int, float, str]


def money(value: MoneyInput) -> Decimal:
    """Convert a value to the application's canonical two-decimal amount."""
    return Decimal(str(value)).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
