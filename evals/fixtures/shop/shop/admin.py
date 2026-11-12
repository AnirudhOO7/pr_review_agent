"""Admin actions."""

from shop.inventory import restock
from shop.users import find_user


def promote_to_admin(email):
    user = find_user(email)
    user.is_admin = True
    return user


def receive_shipment(lines):
    for sku, qty in lines:
        restock(sku, qty)
