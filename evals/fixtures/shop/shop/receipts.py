"""Plain-text receipts."""

from shop.orders import serialize_order
from shop.pricing import format_price
from shop.users import split_full_name


def receipt_line(order):
    data = serialize_order(order)
    return f"Order {data['id']}: {format_price(data['total_cents'])}"


def greeting(user):
    first, last = split_full_name(user.full_name)
    return f"Thanks for your order, {first}!"
