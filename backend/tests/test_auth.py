"""Optional accounts: sign up keeps the plan, sign in works on a new device, ids can't be borrowed."""
import pytest
from fastapi.testclient import TestClient

from backend import auth, db, rate_limit

SETTINGS = {
    "nickname": "Sam",
    "wake_times": {d: "06:45" for d in ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]},
    "school_blocks": {d: ["07:45", "14:45"] for d in ["mon", "tue", "wed", "thu", "fri"]} | {"sat": None, "sun": None},
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "auth.db"))
    monkeypatch.setenv("PACE_NOW", "2026-10-19T15:30:00")
    auth._failures.clear()
    from backend.main import app
    db.init_db()
    with TestClient(app) as c:
        c.headers.update({"Origin": "http://testserver"})
        yield c


def anon(uid):
    return {"X-User-Id": uid}


def new_device():
    from backend.main import app
    client = TestClient(app)
    client.headers.update({"Origin": "http://testserver"})
    return client


def test_password_hashing():
    stored = auth.hash_password("correct horse")
    assert "correct horse" not in stored
    assert auth.verify_password("correct horse", stored)
    assert not auth.verify_password("wrong horse", stored)


def test_signup_keeps_plan_and_login_works_on_new_device(client):
    client.put("/settings", json=SETTINGS, headers=anon("phone-1"))
    client.post("/tasks", json={"title": "Essay", "subject": "english", "due": "2026-10-23T08:00:00",
                                "guess_min": 60}, headers=anon("phone-1"))
    r = client.post("/auth/signup", json={"username": "Sam_42", "password": "longenough"}, headers=anon("phone-1"))
    assert r.status_code == 200 and r.json()["username"] == "sam_42"

    # A second device signs in and sees the same plan.
    with new_device() as other:
        login = other.post("/auth/login", json={"username": "sam_42", "password": "longenough"}).json()
        assert login["user_id"] == "phone-1" and login["has_settings"] is True
        assert "token" not in login
        tasks = other.get("/tasks").json()
        assert [t["title"] for t in tasks] == ["Essay"]
        assert other.get("/auth/me").json() == {"signed_in": True, "username": "sam_42",
                                                 "provider": "password"}


def test_account_id_cannot_be_borrowed_without_signing_in(client):
    client.put("/settings", json=SETTINGS, headers=anon("phone-1"))
    client.post("/auth/signup", json={"username": "sam", "password": "longenough"}, headers=anon("phone-1"))
    with new_device() as other:
        assert other.get("/tasks", headers=anon("phone-1")).status_code == 401


def test_bad_logins(client):
    client.post("/auth/signup", json={"username": "sam", "password": "longenough"}, headers=anon("a"))
    with new_device() as other:
        assert other.post("/auth/login", json={"username": "sam", "password": "nope"}).status_code == 401
        assert other.post("/auth/login", json={"username": "nobody", "password": "longenough"}).status_code == 401
        for _ in range(5):
            other.post("/auth/login", json={"username": "sam", "password": "nope"})
        assert other.post("/auth/login", json={"username": "sam", "password": "longenough"}).status_code == 429


def test_signup_rules(client):
    assert client.post("/auth/signup", json={"username": "ab", "password": "longenough"}, headers=anon("a")).status_code == 422
    assert client.post("/auth/signup", json={"username": "sam", "password": "short"}, headers=anon("a")).status_code == 422
    assert client.post("/auth/signup", json={"username": "sam", "password": "longenough"}, headers=anon("a")).status_code == 200
    with new_device() as other:
        taken = other.post("/auth/signup", json={"username": "SAM", "password": "longenough"}, headers=anon("b"))
    assert taken.status_code == 409 and "taken" in taken.json()["detail"]


def test_common_password_is_rejected(client):
    assert auth.weak_password("password")
    response = client.post("/auth/signup", json={"username": "sam", "password": "password"}, headers=anon("a"))
    assert response.status_code == 422
    assert "common" in response.json()["detail"]


def test_logout_ends_session(client):
    response = client.post("/auth/signup", json={"username": "sam", "password": "longenough"}, headers=anon("a"))
    assert "httponly" in response.headers["set-cookie"].lower()
    assert "samesite=strict" in response.headers["set-cookie"].lower()
    assert client.post("/auth/logout").status_code == 200
    assert client.get("/auth/me", headers=anon("a")).status_code == 401


def test_cookie_is_secure_on_https(client):
    response = client.post("/auth/signup", json={"username": "sam", "password": "longenough"},
                           headers={**anon("a"), "X-Forwarded-Proto": "https"})
    cookie = response.headers["set-cookie"].lower()
    assert "secure" in cookie and "httponly" in cookie and "samesite=strict" in cookie
    assert "token" not in response.json()


def test_cookie_write_requires_same_origin(client):
    client.post("/auth/signup", json={"username": "sam", "password": "longenough"}, headers=anon("a"))
    assert client.put("/settings", json=SETTINGS, headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.put("/settings", json=SETTINGS).status_code == 200


def test_logout_all_revokes_other_device(client):
    client.post("/auth/signup", json={"username": "sam", "password": "longenough"}, headers=anon("a"))
    with new_device() as other:
        assert other.post("/auth/login", json={"username": "sam", "password": "longenough"}).status_code == 200
        assert other.get("/auth/me").status_code == 200
        assert client.post("/auth/logout-all").status_code == 200
        assert other.get("/auth/me").status_code == 401
        assert client.get("/auth/me", headers=anon("a")).status_code == 401


def test_legacy_session_exchanged_once(client):
    with db.connect() as conn:
        conn.execute("INSERT INTO accounts (user_id, username, password_hash, created_at) VALUES (?,?,?,?)",
                     ("old-plan", "sam", auth.hash_password("longenough"), "2026-10-19T15:30:00"))
        token = auth.create_session(conn, "old-plan")
    response = client.post("/auth/migrate", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200 and "token" not in response.json()
    assert client.get("/auth/me").json()["signed_in"] is True
    with db.connect() as conn:
        assert auth.user_for_token(conn, token) is None


def test_ip_limit_uses_trusted_render_header(client, monkeypatch):
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setitem(rate_limit.LIMITS, "/auth/login", (2, 900))
    first = {"CF-Connecting-IP": "198.51.100.10", "X-Forwarded-For": "1.1.1.1"}
    assert client.post("/auth/login", json={"username": "nobody", "password": "wrong"}, headers=first).status_code == 401
    assert client.post("/auth/login", json={"username": "nobody", "password": "wrong"}, headers=first).status_code == 401
    spoof = {**first, "X-Forwarded-For": "2.2.2.2"}
    limited = client.post("/auth/login", json={"username": "nobody", "password": "wrong"}, headers=spoof)
    assert limited.status_code == 429 and int(limited.headers["Retry-After"]) > 0
    second = {"CF-Connecting-IP": "198.51.100.11"}
    assert client.post("/auth/login", json={"username": "nobody", "password": "wrong"}, headers=second).status_code == 401


@pytest.fixture
def google(monkeypatch):
    """Fake Google: credential "good-<sub>" verifies as that sub, anything else fails."""
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client.apps.googleusercontent.com")
    monkeypatch.setattr(auth, "verify_google_credential",
                        lambda cred, cid: cred[5:] if cred.startswith("good-") else None)


GOOD = "good-" + "1" * 21


def test_google_not_configured(client, monkeypatch):
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    assert client.get("/auth/config").json() == {"google_client_id": None}
    assert client.post("/auth/google", json={"credential": GOOD}).status_code == 503


def test_google_new_account_keeps_this_browsers_plan(client, google):
    client.put("/settings", json=SETTINGS, headers=anon("laptop"))
    r = client.post("/auth/google", json={"credential": GOOD}, headers=anon("laptop")).json()
    assert r["user_id"] == "laptop" and r["created"] and r["has_settings"]
    assert client.get("/auth/me").json()["provider"] == "google"
    # The plain id now needs a sign-in, and a second device gets the same plan back.
    with new_device() as other:
        assert other.get("/tasks", headers=anon("laptop")).status_code == 401
        again = other.post("/auth/google", json={"credential": GOOD}, headers=anon("phone")).json()
        assert again["user_id"] == "laptop" and not again["created"]


def test_google_never_takes_over_someone_elses_plan(client, google):
    client.post("/auth/signup", json={"username": "sam", "password": "longenough"}, headers=anon("shared"))
    with new_device() as other:
        r = other.post("/auth/google", json={"credential": GOOD}, headers=anon("shared")).json()
        assert r["user_id"] != "shared" and r["has_settings"] is False


def test_google_bad_token(client, google):
    assert client.post("/auth/google", json={"credential": "bad-" + "x" * 30}).status_code == 401
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM google_accounts").fetchone()[0] == 0


def test_google_stores_no_email(client, google):
    client.post("/auth/google", json={"credential": GOOD}, headers=anon("x"))
    with db.connect() as conn:
        assert [tuple(r.keys()) for r in conn.execute("SELECT * FROM google_accounts").fetchall()] == \
            [("google_sub", "user_id", "created_at")]


def test_demo_plan_can_never_become_an_account(client, google):
    r = client.post("/auth/signup", json={"username": "sam", "password": "longenough"}, headers=anon("demo"))
    assert r.status_code == 409 and "demo" in r.json()["detail"]
    g = client.post("/auth/google", json={"credential": GOOD}, headers=anon("demo")).json()
    assert g["user_id"] != "demo"
    with new_device() as other:
        assert other.get("/auth/me", headers=anon("demo")).json()["signed_in"] is False


def test_delete_me_removes_account(client):
    client.post("/auth/signup", json={"username": "sam", "password": "longenough"}, headers=anon("a"))
    client.delete("/me")
    assert client.post("/auth/login", json={"username": "sam", "password": "longenough"}).status_code == 401
    # username is free again
    assert client.post("/auth/signup", json={"username": "sam", "password": "longenough"}, headers=anon("b")).status_code == 200
