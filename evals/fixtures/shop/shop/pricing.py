"""Price calculation for the checkout flow."""

from shop.coupons import lookup_coupon

DISCOUNTS = {"WELCOME10": 0.10, "VIP25": 0.25}


def get_discount(code):
    """Fractional discount for a promo code; unknown codes get no discount."""
    return DISCOUNTS.get(code, 0.0)


def format_price(cents):
    return f"${cents / 100:.2f}"


def apply_coupon(subtotal_cents, coupon_code):
    coupon = lookup_coupon(coupon_code)
    if coupon is None:
        return subtotal_cents
    return max(0, subtotal_cents - coupon.amount_off_cents)
