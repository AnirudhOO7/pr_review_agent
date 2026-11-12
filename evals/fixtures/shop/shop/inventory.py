"""Stock levels per SKU."""

import threading

_STOCK = {}
_LOCK = threading.Lock()


class OutOfStock(Exception):
    pass


def reserve_stock(sku, qty):
    with _LOCK:
        available = _STOCK.get(sku, 0)
        if available < qty:
            raise OutOfStock(sku)
        _STOCK[sku] = available - qty


def restock(sku, qty):
    with _LOCK:
        _STOCK[sku] = _STOCK.get(sku, 0) + qty
