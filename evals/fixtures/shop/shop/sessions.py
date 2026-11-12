"""Login sessions."""

import secrets

SESSION_HOURS = 12


def session_ttl():
    """Session lifetime in seconds."""
    return SESSION_HOURS * 3600


def new_session(user_id):
    return {"token": secrets.token_urlsafe(32), "user_id": user_id}
