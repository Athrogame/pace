"""Server-checked age screen and parent email consent state."""
import hashlib
import hmac
import os
import secrets
import time
from datetime import date

COOKIE = "pace_age"
MAX_AGE_SECONDS = 365 * 86400


def required():
    return os.environ.get("PACE_REQUIRE_AGE_GATE") == "1"


def secret():
    value = os.environ.get("PACE_AGE_GATE_SECRET", "")
    if len(value) < 32:
        raise RuntimeError("PACE_AGE_GATE_SECRET must have at least 32 characters")
    return value.encode()


def sign(kind, uid=""):
    payload = f"{kind}:{uid}:{int(time.time())}"
    mac = hmac.new(secret(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}:{mac}"


def read(token):
    if not token:
        return None
    try:
        kind, uid, stamp, mac = token.split(":", 3)
        payload = f"{kind}:{uid}:{stamp}"
        expected = hmac.new(secret(), payload.encode(), hashlib.sha256).hexdigest()
        age = time.time() - int(stamp)
        if kind not in {"adult", "child_pending", "child"} or not hmac.compare_digest(mac, expected):
            return None
        if age < -60 or age > MAX_AGE_SECONDS:
            return None
        return kind, uid
    except (ValueError, TypeError):
        return None


def is_under_13(month, year, today=None):
    today = today or date.today()
    if not 1 <= month <= 12 or not 1900 <= year <= today.year:
        raise ValueError("Enter a valid birth month and year")
    # If the birth day is unknown, treat the whole 13th-birthday month as under 13.
    return (year, month) >= (today.year - 13, today.month)


def code_hash(code):
    return hashlib.sha256(code.strip().upper().encode()).hexdigest()


def new_code():
    return secrets.token_urlsafe(24)


def approved(conn, uid):
    return bool(conn.execute(
        "SELECT 1 FROM parent_email_consents WHERE user_id = ? "
        "AND confirmed_at IS NOT NULL AND revoked_at IS NULL",
        (uid,),
    ).fetchone())


def cleanup(conn):
    """Remove unapproved contact addresses after seven days."""
    cutoff = int(time.time()) - 7 * 86400
    conn.execute("DELETE FROM parent_email_consents WHERE confirmed_at IS NULL "
                 "AND COALESCE(accepted_at, requested_at) < ?", (cutoff,))
