"""Small shared rate limiter backed by the same durable database as Pace."""
import hashlib
import hmac
import ipaddress
import os
import time

from fastapi import Request

from . import db


# action -> (requests, window in seconds)
LIMITS = {
    "/auth/signup": (10, 3600),
    "/auth/login": (30, 900),
    "/auth/google": (20, 900),
    "/came-up": (20, 3600),
}


def client_ip(request: Request) -> str:
    # Render's Cloudflare edge overwrites this header. Never trust it locally.
    value = request.headers.get("cf-connecting-ip") if os.environ.get("RENDER") == "true" else None
    try:
        return str(ipaddress.ip_address(value or request.client.host))
    except (ValueError, AttributeError):
        return "unknown"


def check(request: Request) -> int | None:
    """Return retry seconds if limited; otherwise record this request."""
    action = request.url.path
    limit = LIMITS.get(action)
    if request.method != "POST" or limit is None:
        return None
    count, duration = limit
    now = int(time.time())
    window = now - now % duration
    secret = os.environ.get("PACE_AGE_GATE_SECRET", "local-rate-limit-key")
    bucket = hmac.new(secret.encode(), f"{action}:{client_ip(request)}".encode(), hashlib.sha256).hexdigest()
    with db.connect() as conn:
        conn.execute("DELETE FROM rate_limits WHERE window_start < ?", (now - 86400,))
        hits = conn.execute(
            "INSERT INTO rate_limits (bucket, window_start, hits) VALUES (?,?,1) "
            "ON CONFLICT(bucket, window_start) DO UPDATE SET hits = rate_limits.hits + 1 "
            "RETURNING hits", (bucket, window),
        ).fetchone()[0]
    return window + duration - now if hits > count else None
