"""Plain-text direct notice and confirmation for under-13, internal-only plans."""
import os
from urllib.parse import urlsplit

import httpx


def config():
    keys = ("PACE_BREVO_API_KEY", "PACE_BREVO_SENDER")
    missing = [key for key in keys if not os.environ.get(key)]
    if missing:
        raise RuntimeError("Parent email is not configured: " + ", ".join(missing))
    base = (os.environ.get("PACE_PUBLIC_URL") or os.environ.get("RENDER_EXTERNAL_URL") or "").rstrip("/")
    parsed = urlsplit(base)
    if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1"}):
        raise RuntimeError("PACE_PUBLIC_URL or RENDER_EXTERNAL_URL must use HTTPS")
    return base


def send(to, token, *, confirmation=False):
    base = config()
    contact = os.environ["PACE_CONTACT_EMAIL"]
    link = f"{base}/parent-approval#{token}"
    subject = "Pace parent consent confirmation" if confirmation else "Parent consent request for Pace"
    if confirmation:
        content = (
            "A parent or guardian approved an under-13 Pace plan. This follow-up confirms that "
            "choice. Pace would store the child's study plan, assignments, routine and check-ins "
            "for planning. Under-13 plans cannot use Google imports, Google sign-in, or AI, and "
            "are not made public. Render and Supabase provide hosting and storage. You may revoke "
            f"consent and request review or deletion at any time by emailing {contact}. "
            f"Privacy Policy: {base}/privacy-policy\n\n"
            f"To finish confirming the consent, open {link}\n\n"
            "If you did not approve this, do not open the link. Contact us to delete the request."
        )
    else:
        content = (
            "Someone entered this address as a parent or guardian contact for an under-13 Pace "
            "plan. Pace has not collected their plan information. If you consent, Pace will "
            "store the child's study plan, assignments, routine and sleep/energy/stress check-ins "
            "to provide schedules and local coach messages. Under-13 plans cannot use Google "
            "imports, Google sign-in, or AI, and are not made public. Render and Supabase provide "
            "hosting and storage. You can review or delete the child's data, or revoke consent, "
            f"at any time by emailing {contact}. Privacy Policy: {base}/privacy-policy\n\n"
            f"To give consent, open {link} and select I consent. We will send a separate "
            "confirmation message later. If you do not consent, ignore this request; the "
            "request expires after seven days, and the contact address is removed during cleanup."
        )
    response = httpx.post("https://api.brevo.com/v3/smtp/email",
                          headers={"api-key": os.environ["PACE_BREVO_API_KEY"]},
                          json={"sender": {"name": "Pace", "email": os.environ["PACE_BREVO_SENDER"]},
                                "to": [{"email": to}], "subject": subject, "textContent": content},
                          timeout=10.0)
    response.raise_for_status()
