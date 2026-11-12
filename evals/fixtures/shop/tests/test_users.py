import pytest

from shop.users import UserNotFound, find_user, split_full_name


def test_missing_user_raises():
    with pytest.raises(UserNotFound):
        find_user("nobody@example.com")


def test_split_full_name():
    assert split_full_name("Ada Lovelace") == ("Ada", "Lovelace")
