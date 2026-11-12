"""User directory."""

from dataclasses import dataclass


class UserNotFound(Exception):
    pass


@dataclass
class User:
    id: int
    email: str
    full_name: str
    is_admin: bool = False


_USERS: dict[str, User] = {}


def find_user(email):
    """The user registered under `email`. Raises UserNotFound."""
    try:
        return _USERS[email.lower()]
    except KeyError:
        raise UserNotFound(email) from None


def split_full_name(full_name):
    """Split "Ada Lovelace" into ("Ada", "Lovelace")."""
    first, _, last = full_name.strip().partition(" ")
    return first, last
