"""Login and session issuing."""

import time

from shop.sessions import new_session, session_ttl
from shop.users import UserNotFound, find_user


def login(email, store):
    try:
        user = find_user(email)
    except UserNotFound:
        return None
    session = new_session(user.id)
    session["expires_at"] = time.time() + session_ttl()
    store.save(session)
    return session
