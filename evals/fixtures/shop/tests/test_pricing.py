from shop.pricing import format_price, get_discount


def test_unknown_code_has_no_discount():
    assert get_discount("NOPE") == 0.0


def test_format_price():
    assert format_price(1999) == "$19.99"
