"""Fixed-amount coupons."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Coupon:
    code: str
    amount_off_cents: int


_COUPONS = {"SAVE5": Coupon("SAVE5", 500), "SAVE20": Coupon("SAVE20", 2000)}


def lookup_coupon(code):
    """Coupon for `code`, or None if it doesn't exist."""
    return _COUPONS.get(code)
