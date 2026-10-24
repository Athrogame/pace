"""Optional accounts: username + password, no email (keeps the "nickname only" privacy rule).

Passwords are hashed with scrypt and a per-user salt. Sessions are random tokens; only their
SHA-256 is stored, so a leaked database can't be used to sign in."""
import hashlib
import hmac
import re
import secrets
import time
from pathlib import Path

USERNAME_RE = re.compile(r"^[a-z0-9_]{3,24}$")
SESSION_DAYS = 90
SESSION_COOKIE = "pace_session"
MAX_FAILURES = 5
FAILURE_WINDOW_S = 15 * 60

_failures: dict = {}   # username -> [timestamps]; in memory is enough for one small server
COMMON_PASSWORDS = frozenset(
    word.casefold() for word in
    (Path(__file__).parent / "data" / "common_passwords.txt").read_text(encoding="utf-8").splitlines()
)


def weak_password(password: str) -> bool:
    return password.casefold() in COMMON_PASSWORDS


def hash_password(password: str, salt: bytes = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    check = hash_password(password, bytes.fromhex(salt_hex)).split("$")[1]
    return hmac.compare_digest(check, digest_hex)


# Used when the username doesn't exist, so a wrong username takes as long as a wrong password.
_DUMMY_HASH = hash_password(secrets.token_hex(8))


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(conn, user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    now = int(time.time())
    conn.execute("INSERT INTO sessions (token_hash, user_id, created_at, expires_at) VALUES (?,?,?,?)",
                 (token_hash(token), user_id, now, now + SESSION_DAYS * 86400))
    return token


def user_for_token(conn, token: str):
    row = conn.execute("SELECT user_id, expires_at FROM sessions WHERE token_hash = ?",
                       (token_hash(token),)).fetchone()
    if row is None or row["expires_at"] < time.time():
        return None
    return row["user_id"]


def delete_session(conn, token: str) -> None:
    conn.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash(token),))


def account_for_user(conn, user_id: str):
    """{"provider": "password"|"google", "username": str|None}, or None for an anonymous plan."""
    row = conn.execute("SELECT username FROM accounts WHERE user_id = ?", (user_id,)).fetchone()
    if row:
        return {"provider": "password", "username": row["username"]}
    if conn.execute("SELECT 1 FROM google_accounts WHERE user_id = ?", (user_id,)).fetchone():
        return {"provider": "google", "username": None}
    return None


# ---------- Sign in with Google ----------

GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}
TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"


def verify_google_credential(credential: str, client_id: str):
    """Checks a Google ID token with Google's tokeninfo endpoint. Returns the account's "sub"
    (a stable number, not an email), or None if the token isn't valid for this app."""
    import httpx
    try:
        r = httpx.get(TOKENINFO_URL, params={"id_token": credential}, timeout=5.0)
    except httpx.HTTPError:
        return None
    if r.status_code != 200:
        return None
    claims = r.json()
    if claims.get("aud") != client_id or claims.get("iss") not in GOOGLE_ISSUERS:
        return None
    try:
        if int(claims.get("exp", 0)) < time.time():
            return None
    except ValueError:
        return None
    return claims.get("sub") or None


def too_many_failures(username: str) -> bool:
    now = time.time()
    recent = [t for t in _failures.get(username, []) if now - t < FAILURE_WINDOW_S]
    _failures[username] = recent
    return len(recent) >= MAX_FAILURES


def record_failure(username: str) -> None:
    _failures.setdefault(username, []).append(time.time())


def clear_failures(username: str) -> None:
    _failures.pop(username, None)
