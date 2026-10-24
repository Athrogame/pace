"""Security headers on every response (Take9 pledge, see SECURITY.md)."""
import pytest
from fastapi.testclient import TestClient

from backend import db


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "sec.db"))
    from backend.main import app
    db.init_db()
    with TestClient(app) as c:
        yield c


def test_headers_on_pages_and_api(client):
    for path in ["/", "/app.js", "/safety", "/auth/config"]:
        r = client.get(path)
        assert r.status_code == 200, path
        csp = r.headers["content-security-policy"]
        assert "frame-ancestors 'none'" in csp and "object-src 'none'" in csp
        assert "https://accounts.google.com/gsi/client" in csp     # Google sign-in still allowed
        assert r.headers["x-content-type-options"] == "nosniff"
        assert r.headers["x-frame-options"] == "DENY"
        assert "camera=()" in r.headers["permissions-policy"]


def test_caching_rules(client):
    assert client.get("/app.js").headers["cache-control"] == "no-cache"
    assert client.get("/auth/config").headers["cache-control"] == "no-store"


def test_hsts_only_over_https(client):
    assert "strict-transport-security" not in client.get("/").headers
    secure = client.get("/", headers={"X-Forwarded-Proto": "https"})
    assert secure.headers["strict-transport-security"].startswith("max-age=31536000")


def test_manifest_and_icons_served(client):
    manifest = client.get("/manifest.json")
    assert manifest.status_code == 200 and manifest.json()["display"] == "standalone"
    for icon in manifest.json()["icons"]:
        r = client.get("/" + icon["src"])
        assert r.status_code == 200 and r.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_public_legal_pages_require_a_real_contact(client, monkeypatch):
    monkeypatch.delenv("PACE_CONTACT_EMAIL", raising=False)
    assert client.get("/privacy-policy").status_code == 503
    monkeypatch.setenv("PACE_CONTACT_EMAIL", "pace-help@example.org")
    for path in ["/privacy-policy", "/terms", "/parent-approval"]:
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")
        assert "pace-help@example.org" in response.text
        assert "{{CONTACT_EMAIL}}" not in response.text
    assert 'href="/privacy-policy"' in client.get("/").text


def test_public_deployment_requires_contact(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "sec.db"))
    monkeypatch.setenv("PACE_REQUIRE_LEGAL_CONTACT", "1")
    monkeypatch.delenv("PACE_CONTACT_EMAIL", raising=False)
    from backend.main import app
    with pytest.raises(RuntimeError, match="PACE_CONTACT_EMAIL"):
        with TestClient(app):
            pass
