"""Turns a cart into an order."""

from shop.inventory import reserve_stock
from shop.pricing import apply_coupon, format_price, get_discount


def order_total(items, promo_code):
    subtotal = sum(item.price_cents * item.qty for item in items)
    discounted = subtotal * (1 - get_discount(promo_code))
    return round(discounted)


def place_order(cart, promo_code=None, coupon_code=None):
    for item in cart.items:
        reserve_stock(item.sku, item.qty)
    total = apply_coupon(order_total(cart.items, promo_code), coupon_code)
    return {"total_cents": total, "display_total": format_price(total)}
