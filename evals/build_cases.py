"""Generate the eval case files from readable before/after source.

    python -m evals.build_cases

Hand-writing unified diffs (and counting their line numbers) is error-prone, so
cases are authored here as source code. A trailing `#@bug` on a line of the
*after* text marks the planted bug; the marker is stripped before the diff is
built and its new-file line number becomes the ground truth. Diffs come from
difflib, so they are valid unified diffs with correct hunk headers.

Two files are written:
  - evals/cases/general.json: self-contained diffs (no repository needed)
  - evals/cases/context.json: diffs against the fixture repo in
    evals/fixtures/shop, where the defect (or its absence) is only visible in
    callers elsewhere in that repo. These measure structural retrieval.

`seed.json` (the original 12 cases) is left untouched.
"""

import difflib
import json
from pathlib import Path

EVALS_DIR = Path(__file__).parent
CASES_DIR = EVALS_DIR / "cases"
SHOP = EVALS_DIR / "fixtures" / "shop"
BUG_MARK = "#@bug"


def build_diff(path: str, before: str, after: str) -> tuple[str, list[int]]:
    """Unified diff for `path` plus the new-file lines tagged with BUG_MARK."""
    bug_lines: list[int] = []
    clean_after: list[str] = []
    for i, line in enumerate(after.splitlines(), start=1):
        if line.rstrip().endswith(BUG_MARK):
            bug_lines.append(i)
            line = line.rstrip()[: -len(BUG_MARK)].rstrip()
        clean_after.append(line)

    before_lines = before.splitlines() if before else []
    diff_lines = difflib.unified_diff(
        before_lines,
        clean_after,
        fromfile=f"a/{path}" if before else "/dev/null",
        tofile=f"b/{path}",
        n=3,
        lineterm="",
    )
    return "\n".join(diff_lines) + "\n", bug_lines


def make_case(
    case_id: str,
    path: str,
    before: str,
    after: str,
    *,
    bug_type: str | None = None,
    category: str | None = None,
    repo_path: str | None = None,
) -> dict:
    diff, bug_lines = build_diff(path, _dedent(before), _dedent(after))
    label = "buggy" if bug_type else "clean"
    if label == "buggy" and not bug_lines:
        raise ValueError(f"{case_id}: buggy case has no {BUG_MARK} marker")
    if label == "clean" and bug_lines:
        raise ValueError(f"{case_id}: clean case has a {BUG_MARK} marker")
    case: dict = {"id": case_id, "label": label, "diff": diff}
    if label == "buggy":
        case["expected"] = {
            "file": path,
            "lines": bug_lines,
            "bug_type": bug_type,
            "category": category,
        }
    if repo_path:
        case["repo_path"] = repo_path
    return case


def edit_fixture(path: str, edits: list[tuple[str, str]]) -> tuple[str, str]:
    """(before, after) for a fixture file with literal search/replace edits."""
    before = (SHOP / path).read_text(encoding="utf-8")
    after = before
    for old, new in edits:
        if after.count(old) != 1:
            raise ValueError(f"Edit target not unique in {path}: {old!r}")
        after = after.replace(old, new)
    return before, after


def _dedent(text: str) -> str:
    import textwrap

    return textwrap.dedent(text).lstrip("\n")


# --------------------------------------------------------------------------
# General cases: self-contained, paired buggy/clean where possible.
# --------------------------------------------------------------------------

GENERAL = [
    # 1. Path traversal vs. a contained join
    make_case(
        "buggy_path_traversal",
        "app/files/download.py",
        """
        import os

        from flask import abort, send_file

        UPLOAD_DIR = "/srv/uploads"


        def download(filename):
            if not filename:
                abort(400)
            return send_file(UPLOAD_DIR + "/" + filename)
        """,
        """
        import os

        from flask import abort, send_file

        UPLOAD_DIR = "/srv/uploads"


        def download(filename):
            if not filename:
                abort(400)
            path = os.path.join(UPLOAD_DIR, filename)  #@bug
            if not os.path.isfile(path):
                abort(404)
            return send_file(path)
        """,
        bug_type="path-traversal",
        category="security",
    ),
    make_case(
        "clean_safe_download",
        "app/files/download.py",
        """
        from pathlib import Path

        from flask import abort, send_file

        UPLOAD_DIR = Path("/srv/uploads")


        def download(filename):
            return send_file(UPLOAD_DIR / filename)
        """,
        """
        from pathlib import Path

        from flask import abort, send_file

        UPLOAD_DIR = Path("/srv/uploads").resolve()


        def download(filename):
            if not filename:
                abort(400)
            path = (UPLOAD_DIR / filename).resolve()
            if not path.is_relative_to(UPLOAD_DIR) or not path.is_file():
                abort(404)
            return send_file(path)
        """,
    ),
    # 2. Unsafe deserialization vs. signed JSON
    make_case(
        "buggy_pickle_session",
        "app/web/session.py",
        """
        import base64
        import json


        def load_session(cookie_value):
            if not cookie_value:
                return {}
            return json.loads(base64.urlsafe_b64decode(cookie_value))
        """,
        """
        import base64
        import pickle


        def load_session(cookie_value):
            if not cookie_value:
                return {}
            return pickle.loads(base64.urlsafe_b64decode(cookie_value))  #@bug
        """,
        bug_type="insecure-deserialization",
        category="security",
    ),
    make_case(
        "clean_signed_session",
        "app/web/session.py",
        """
        import base64
        import json


        def load_session(cookie_value):
            if not cookie_value:
                return {}
            return json.loads(base64.urlsafe_b64decode(cookie_value))
        """,
        """
        import base64
        import hashlib
        import hmac
        import json

        from app.config import SECRET_KEY


        def load_session(cookie_value):
            if not cookie_value or "." not in cookie_value:
                return {}
            payload, signature = cookie_value.rsplit(".", 1)
            expected = hmac.new(SECRET_KEY, payload.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected, signature):
                return {}
            return json.loads(base64.urlsafe_b64decode(payload))
        """,
    ),
    # 3. Weak password hashing vs. scrypt
    make_case(
        "buggy_md5_password",
        "app/auth/passwords.py",
        "",
        """
        import hashlib


        def hash_password(password):
            return hashlib.md5(password.encode()).hexdigest()  #@bug


        def verify_password(password, stored_hash):
            return hash_password(password) == stored_hash
        """,
        bug_type="weak-crypto",
        category="security",
    ),
    make_case(
        "clean_scrypt_password",
        "app/auth/passwords.py",
        "",
        """
        import hashlib
        import hmac
        import os


        def hash_password(password):
            salt = os.urandom(16)
            digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
            return salt.hex() + ":" + digest.hex()


        def verify_password(password, stored):
            salt_hex, digest_hex = stored.split(":")
            digest = hashlib.scrypt(
                password.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1
            )
            return hmac.compare_digest(digest.hex(), digest_hex)
        """,
    ),
    # 4. Swallowed payment failure vs. handled one
    make_case(
        "buggy_swallowed_payment_error",
        "app/billing/capture.py",
        """
        from app.billing.gateway import charge


        def capture(order):
            charge(order.customer_id, order.total_cents)
            order.status = "paid"
            order.save()
        """,
        """
        import logging

        from app.billing.gateway import charge

        log = logging.getLogger(__name__)


        def capture(order):
            try:
                charge(order.customer_id, order.total_cents)
            except Exception:  #@bug
                log.warning("charge failed for order %s", order.id)  #@bug
            order.status = "paid"
            order.save()
        """,
        bug_type="error-handling",
        category="correctness",
    ),
    make_case(
        "clean_payment_error_handled",
        "app/billing/capture.py",
        """
        from app.billing.gateway import charge


        def capture(order):
            charge(order.customer_id, order.total_cents)
            order.status = "paid"
            order.save()
        """,
        """
        import logging

        from app.billing.gateway import CardDeclined, charge

        log = logging.getLogger(__name__)


        def capture(order):
            try:
                charge(order.customer_id, order.total_cents)
            except CardDeclined:
                log.info("card declined for order %s", order.id)
                order.status = "payment_failed"
            else:
                order.status = "paid"
            order.save()
        """,
    ),
    # 5. Always-true permission check vs. set membership
    make_case(
        "buggy_or_condition_authz",
        "app/projects/permissions.py",
        """
        def can_delete_project(user, project):
            return user.id == project.owner_id
        """,
        """
        def can_delete_project(user, project):
            if user.role == "admin" or "owner":  #@bug
                return True
            return user.id == project.owner_id
        """,
        bug_type="logic-error",
        category="security",
    ),
    make_case(
        "clean_role_membership",
        "app/projects/permissions.py",
        """
        def can_delete_project(user, project):
            return user.id == project.owner_id
        """,
        """
        PRIVILEGED_ROLES = {"admin", "owner"}


        def can_delete_project(user, project):
            if user.role in PRIVILEGED_ROLES:
                return True
            return user.id == project.owner_id
        """,
    ),
    # 6. Naive vs. aware datetime comparison
    make_case(
        "buggy_naive_datetime",
        "app/auth/tokens.py",
        """
        from datetime import datetime, timezone


        def is_expired(token):
            # token.expires_at is a timezone-aware UTC datetime
            return token.expires_at <= datetime.now(timezone.utc)
        """,
        """
        from datetime import datetime, timedelta, timezone

        GRACE = timedelta(seconds=30)


        def is_expired(token):
            # token.expires_at is a timezone-aware UTC datetime
            return token.expires_at + GRACE <= datetime.now()  #@bug
        """,
        bug_type="datetime",
        category="correctness",
    ),
    make_case(
        "clean_aware_datetime",
        "app/auth/tokens.py",
        """
        from datetime import datetime, timezone


        def is_expired(token):
            # token.expires_at is a timezone-aware UTC datetime
            return token.expires_at <= datetime.now(timezone.utc)
        """,
        """
        from datetime import datetime, timedelta, timezone

        GRACE = timedelta(seconds=30)


        def is_expired(token, now=None):
            # token.expires_at is a timezone-aware UTC datetime
            now = now or datetime.now(timezone.utc)
            return token.expires_at + GRACE <= now
        """,
    ),
    # 7. Removing from a list while iterating vs. rebuilding it
    make_case(
        "buggy_mutate_while_iterating",
        "app/cart/cleanup.py",
        "",
        """
        def drop_empty_lines(cart):
            for line in cart.lines:
                if line.qty == 0:
                    cart.lines.remove(line)  #@bug
            return cart
        """,
        bug_type="iteration-mutation",
        category="correctness",
    ),
    make_case(
        "clean_rebuild_list",
        "app/cart/cleanup.py",
        "",
        """
        def drop_empty_lines(cart):
            cart.lines = [line for line in cart.lines if line.qty > 0]
            return cart
        """,
    ),
    # 8. Pagination loop that never advances vs. one that does
    make_case(
        "buggy_infinite_pagination",
        "app/sync/fetch.py",
        "",
        """
        def fetch_all(client):
            items = []
            cursor = None
            while True:
                page = client.list_items(cursor=cursor)
                items.extend(page["items"])
                if not page.get("next_cursor"):
                    break
                cursor = page.get("cursor")  #@bug
            return items
        """,
        bug_type="infinite-loop",
        category="correctness",
    ),
    make_case(
        "clean_bounded_pagination",
        "app/sync/fetch.py",
        "",
        """
        MAX_PAGES = 1000


        def fetch_all(client):
            items = []
            cursor = None
            for _ in range(MAX_PAGES):
                page = client.list_items(cursor=cursor)
                items.extend(page["items"])
                cursor = page.get("next_cursor")
                if not cursor:
                    break
            return items
        """,
    ),
    # 9. JS: missing await vs. awaited
    make_case(
        "buggy_missing_await",
        "src/routes/profile.js",
        """
        export async function getProfile(req, res) {
          const user = await db.findUser(req.params.id);
          res.json(user);
        }
        """,
        """
        export async function getProfile(req, res) {
          const user = db.findUser(req.params.id);  #@bug
          if (!user) {
            return res.status(404).json({ error: "not found" });
          }
          res.json({ id: user.id, name: user.name });
        }
        """,
        bug_type="async",
        category="correctness",
    ),
    make_case(
        "clean_awaited_lookup",
        "src/routes/profile.js",
        """
        export async function getProfile(req, res) {
          const user = await db.findUser(req.params.id);
          res.json(user);
        }
        """,
        """
        export async function getProfile(req, res) {
          const user = await db.findUser(req.params.id);
          if (!user) {
            return res.status(404).json({ error: "not found" });
          }
          res.json({ id: user.id, name: user.name });
        }
        """,
    ),
    # 10. JS: innerHTML with user content vs. textContent
    make_case(
        "buggy_xss_innerhtml",
        "src/ui/comments.js",
        "",
        """
        export function renderComment(list, comment) {
          const item = document.createElement("li");
          item.className = "comment";
          item.innerHTML = `<b>${comment.author}</b>: ${comment.body}`;  #@bug
          list.appendChild(item);
        }
        """,
        bug_type="xss",
        category="security",
    ),
    make_case(
        "clean_textcontent",
        "src/ui/comments.js",
        "",
        """
        export function renderComment(list, comment) {
          const item = document.createElement("li");
          item.className = "comment";
          const author = document.createElement("b");
          author.textContent = comment.author;
          item.append(author, `: ${comment.body}`);
          list.appendChild(item);
        }
        """,
    ),
]


# --------------------------------------------------------------------------
# Context cases: diffs against evals/fixtures/shop. Each buggy change looks
# deliberate in isolation; the break is in a caller elsewhere in the repo.
# --------------------------------------------------------------------------

REPO = "../fixtures/shop"


def context_case(case_id: str, path: str, edits, **kwargs) -> dict:
    before, after = edit_fixture(path, edits)
    return make_case(case_id, path, before, after, repo_path=REPO, **kwargs)


CONTEXT = [
    context_case(
        "ctx_buggy_discount_returns_none",
        "shop/pricing.py",
        [(
            '''def get_discount(code):
    """Fractional discount for a promo code; unknown codes get no discount."""
    return DISCOUNTS.get(code, 0.0)''',
            '''def get_discount(code):
    """Fractional discount for a promo code, or None for an unknown code."""
    if code not in DISCOUNTS:
        return None  #@bug
    return DISCOUNTS[code]''',
        )],
        bug_type="caller-contract",
        category="correctness",
    ),
    context_case(
        "ctx_buggy_reserve_stock_required_param",
        "shop/inventory.py",
        [(
            '''def reserve_stock(sku, qty):
    with _LOCK:
        available = _STOCK.get(sku, 0)
        if available < qty:
            raise OutOfStock(sku)''',
            '''def reserve_stock(sku, qty, warehouse_id):  #@bug
    with _LOCK:
        available = _STOCK.get(sku, 0)
        if available < qty:
            raise OutOfStock(f"{sku} at warehouse {warehouse_id}")''',
        )],
        bug_type="caller-contract",
        category="correctness",
    ),
    context_case(
        "ctx_buggy_session_ttl_timedelta",
        "shop/sessions.py",
        [
            ("import secrets\n", "import secrets\nfrom datetime import timedelta\n"),
            (
                '''    """Session lifetime in seconds."""
    return SESSION_HOURS * 3600''',
                '''    """Session lifetime."""
    return timedelta(hours=SESSION_HOURS)  #@bug''',
            ),
        ],
        bug_type="caller-contract",
        category="correctness",
    ),
    context_case(
        "ctx_buggy_find_user_returns_none",
        "shop/users.py",
        [(
            '''    """The user registered under `email`. Raises UserNotFound."""
    try:
        return _USERS[email.lower()]
    except KeyError:
        raise UserNotFound(email) from None''',
            '''    """The user registered under `email`, or None."""
    return _USERS.get(email.lower())  #@bug''',
        )],
        bug_type="caller-contract",
        category="correctness",
    ),
    context_case(
        "ctx_buggy_serialize_key_rename",
        "shop/orders.py",
        [('''        "total_cents": order.total_cents,''', '''        "amount_cents": order.total_cents,  #@bug''')],
        bug_type="caller-contract",
        category="correctness",
    ),
    context_case(
        "ctx_buggy_split_name_order",
        "shop/users.py",
        [(
            '''def split_full_name(full_name):
    """Split "Ada Lovelace" into ("Ada", "Lovelace")."""
    first, _, last = full_name.strip().partition(" ")
    return first, last''',
            '''def split_full_name(full_name):
    """Split "Ada Lovelace" into ("Lovelace", "Ada") for surname sorting."""
    first, _, last = full_name.strip().partition(" ")
    return last, first  #@bug''',
        )],
        bug_type="caller-contract",
        category="correctness",
    ),
    # Clean: changes that look risky but every caller is compatible.
    context_case(
        "ctx_clean_format_price_currency",
        "shop/pricing.py",
        [(
            '''def format_price(cents):
    return f"${cents / 100:.2f}"''',
            '''CURRENCY_SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£"}


def format_price(cents, currency="USD"):
    symbol = CURRENCY_SYMBOLS.get(currency, currency + " ")
    return f"{symbol}{cents / 100:.2f}"''',
        )],
    ),
    context_case(
        "ctx_clean_lookup_coupon_normalized",
        "shop/coupons.py",
        [(
            '''    """Coupon for `code`, or None if it doesn't exist."""
    return _COUPONS.get(code)''',
            '''    """Coupon for `code` (case-insensitive), or None if it doesn't exist."""
    if not code:
        return None
    return _COUPONS.get(code.strip().upper())''',
        )],
    ),
    context_case(
        "ctx_clean_session_ttl_constant",
        "shop/sessions.py",
        [
            ("SESSION_HOURS = 12\n", "SESSION_HOURS = 12\nSESSION_TTL_SECONDS = SESSION_HOURS * 60 * 60\n"),
            ("    return SESSION_HOURS * 3600", "    return SESSION_TTL_SECONDS"),
        ],
    ),
    context_case(
        "ctx_clean_serialize_add_field",
        "shop/orders.py",
        [('''        "status": order.status,''', '''        "status": order.status,
        "currency": "USD",''')],
    ),
    context_case(
        "ctx_clean_find_user_strip",
        "shop/users.py",
        [("        return _USERS[email.lower()]", "        return _USERS[email.strip().lower()]")],
    ),
]


def main() -> None:
    outputs = {"general.json": GENERAL, "context.json": CONTEXT}
    for name, cases in outputs.items():
        path = CASES_DIR / name
        path.write_text(json.dumps(cases, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        buggy = sum(1 for c in cases if c["label"] == "buggy")
        print(f"Wrote {len(cases)} cases ({buggy} buggy) to {path}")


if __name__ == "__main__":
    main()
