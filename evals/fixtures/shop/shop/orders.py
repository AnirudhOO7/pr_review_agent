"""Order serialization for the API and receipts."""


def serialize_order(order):
    return {
        "id": order.id,
        "total_cents": order.total_cents,
        "status": order.status,
    }
