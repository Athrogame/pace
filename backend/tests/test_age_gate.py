"""Parent consent never unlocks a child plan from an email address alone."""
import time

from fastapi.testclient import TestClient

from backend import db


def test_parent_email_requires_two_actions_and_blocks_google(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "age.db"))
    monkeypatch.setenv("PACE_REQUIRE_AGE_GATE", "1")
    monkeypatch.setenv("PACE_AGE_GATE_SECRET", "a" * 40)
    from backend import parent_mail
    from backend.main import app
    monkeypatch.setattr(parent_mail, "config", lambda: "http://localhost")
    sent = []
    monkeypatch.setattr(parent_mail, "send", lambda email, token, **kw: sent.append((email, token, kw)))

    with TestClient(app) as child, TestClient(app) as parent:
        assert child.get("/settings", headers={"X-User-Id": "child"}).status_code == 403
        start = child.post("/age/start", json={"birth_month": 1, "birth_year": 2020})
        assert start.status_code == 200 and start.json()["child"]
        assert child.get("/settings", headers={"X-User-Id": "child"}).status_code == 403
        request = child.post("/age/request-parent", json={"parent_email": "parent@example.org"})
        assert request.status_code == 200
        assert len(sent) == 1
        assert child.get("/settings", headers={"X-User-Id": "child"}).status_code == 403

        first = parent.post("/age/parent-decision", json={"token": sent[0][1]})
        assert first.status_code == 200 and first.json()["stage"] == "accepted"
        assert child.get("/age/status").json()["verified"] is False
        with db.connect() as conn:
            conn.execute("UPDATE parent_email_consents SET accepted_at = ?", (int(time.time()) - 86401,))
        child.get("/age/status")
        assert len(sent) == 2 and sent[1][2]["confirmation"]
        second = parent.post("/age/parent-decision", json={"token": sent[1][1]})
        assert second.status_code == 200 and second.json()["stage"] == "confirmed"
        status = child.get("/age/status").json()
        assert status["verified"] and status["child"] and status["user_id"]
        assert child.get("/settings", headers={"X-User-Id": status["user_id"]}).status_code == 404
        assert child.get("/settings", headers={"X-User-Id": "different"}).status_code == 403
        assert child.post("/auth/google", json={"credential": "x"}).status_code == 403
        assert child.post("/tasks/google/suggest", json={"tasks": []}).status_code == 403
        from backend import decision_coach
        monkeypatch.setattr(decision_coach, "_call_ai", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("child data reached AI")))
        settings = {"timezone": "America/New_York", "wake_times": {day: "07:00" for day in
                    ("mon", "tue", "wed", "thu", "fri", "sat", "sun")},
                    "school_blocks": {day: None for day in
                    ("mon", "tue", "wed", "thu", "fri", "sat", "sun")}}
        assert child.put("/settings", headers={"X-User-Id": status["user_id"]}, json=settings).status_code == 200
        chat = child.post("/decision/coach", headers={"X-User-Id": status["user_id"]},
                          json={"message": "Which should I choose?", "option_a": "rest", "option_b": "study"}).json()
        assert chat["source"] == "fallback"
        assert child.delete("/me", headers={"X-User-Id": status["user_id"]}).status_code == 200
        assert child.get("/age/status").json()["verified"] is False


def test_older_user_can_pass_neutral_age_screen(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "age.db"))
    monkeypatch.setenv("PACE_REQUIRE_AGE_GATE", "1")
    monkeypatch.setenv("PACE_AGE_GATE_SECRET", "b" * 40)
    from backend import parent_mail
    from backend.main import app
    monkeypatch.setattr(parent_mail, "config", lambda: "http://localhost")
    with TestClient(app) as client:
        assert client.post("/age/start", json={"birth_month": 1, "birth_year": 2000}).json()["verified"]
        assert client.get("/settings", headers={"X-User-Id": "adult-plan"}).status_code == 404


def test_pending_parent_request_can_be_cancelled(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "cancel.db"))
    monkeypatch.setenv("PACE_REQUIRE_AGE_GATE", "1")
    monkeypatch.setenv("PACE_AGE_GATE_SECRET", "c" * 40)
    from backend import parent_mail
    from backend.main import app
    monkeypatch.setattr(parent_mail, "config", lambda: "http://localhost")
    monkeypatch.setattr(parent_mail, "send", lambda *args, **kwargs: None)
    with TestClient(app) as client:
        client.post("/age/start", json={"birth_month": 1, "birth_year": 2020})
        assert client.post("/age/request-parent", json={"parent_email": "parent@example.org"}).status_code == 200
        assert client.get("/age/status").json()["awaiting_parent"]
        assert client.delete("/age/pending").status_code == 200
        assert not client.get("/age/status").json()["pending"]
        with db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM parent_email_consents").fetchone()[0] == 0


def test_parent_mail_uses_https_api(monkeypatch):
    from backend import parent_mail
    monkeypatch.setenv("PACE_BREVO_API_KEY", "test-key")
    monkeypatch.setenv("PACE_BREVO_SENDER", "pace@example.org")
    monkeypatch.setenv("PACE_PUBLIC_URL", "https://pace.example.org")
    monkeypatch.setenv("PACE_CONTACT_EMAIL", "help@example.org")
    calls = []

    class Response:
        def raise_for_status(self):
            pass

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return Response()

    monkeypatch.setattr(parent_mail.httpx, "post", fake_post)
    parent_mail.send("parent@example.org", "secret-token")
    assert calls[0][0] == "https://api.brevo.com/v3/smtp/email"
    assert calls[0][1]["json"]["to"] == [{"email": "parent@example.org"}]
    assert "/parent-approval#secret-token" in calls[0][1]["json"]["textContent"]


def test_parent_mail_uses_render_public_url(monkeypatch):
    from backend import parent_mail
    monkeypatch.delenv("PACE_PUBLIC_URL", raising=False)
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://pace.onrender.com")
    monkeypatch.setenv("PACE_BREVO_API_KEY", "test-key")
    monkeypatch.setenv("PACE_BREVO_SENDER", "pace@example.org")
    assert parent_mail.config() == "https://pace.onrender.com"
