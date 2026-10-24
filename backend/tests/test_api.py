"""Route-level tests: decision helper, red button, undo, rebalance, coach limits."""
import pytest
from fastapi.testclient import TestClient

from backend import db

NOW = "2026-10-19T15:30:00"   # Monday afternoon


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("PACE_NOW", NOW)
    monkeypatch.delenv("AI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from backend.main import app
    from backend.seed_demo import seed
    from datetime import date
    db.init_db()
    seed("demo", date(2026, 10, 19))
    with TestClient(app) as c:
        c.headers["X-User-Id"] = "demo"
        yield c


EXTRA = {"kind": "shift", "title": "Extra shift", "start": "2026-10-21T15:15:00", "end": "2026-10-21T21:30:00"}


def nights(plan):
    return {n["date"]: n["status"] for n in plan["nights"]}


def test_demo_clock_only_pins_the_demo(client, monkeypatch):
    from backend.timeutil import local_now
    monkeypatch.delenv("PACE_NOW")
    monkeypatch.setenv("PACE_DEMO_NOW", "2026-10-19T15:30:00")
    assert local_now(user_id="demo").isoformat() == "2026-10-19T15:30:00"
    # Everyone else follows the real clock (within a couple of minutes of "now" in New York).
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    real = datetime.now(ZoneInfo("America/New_York")).replace(tzinfo=None)
    assert abs(local_now(user_id="someone-else") - real) < timedelta(minutes=2)


def test_calendar_weeks_include_past_days_with_reported_sleep(client, monkeypatch):
    monkeypatch.setenv("PACE_NOW", "2026-10-24T10:00:00")          # a Saturday
    client.post("/checkins", json={"sleep_min": 360, "energy": 3, "stress": 3})   # Sat morning: 6 hr
    plan = client.get("/plan?weeks=true").json()
    assert plan["week_start"] == "2026-10-19"
    assert [d["date"] for d in plan["past_days"]] == [f"2026-10-{d}" for d in range(19, 24)]   # Mon-Fri
    assert plan["days"][0]["date"] == "2026-10-24" and plan["days"][-1]["date"] == "2026-11-01"
    friday_night = next(n for n in plan["past_nights"] if n["date"] == "2026-10-23")
    assert friday_night["sleep_min"] == 360 and friday_night["status"] == "red" and friday_night["reported"]
    monday_night = next(n for n in plan["past_nights"] if n["date"] == "2026-10-19")
    assert monday_night["sleep_min"] is None and monday_night["status"] == "unknown"
    assert all(d["past"] and d["used_min"] == 0 for d in plan["past_days"])


def test_calendar_weeks_on_a_monday_have_no_past_days(client):
    plan = client.get("/plan?weeks=true").json()       # NOW is Monday Oct 19
    assert plan["past_days"] == [] and len(plan["days"]) == 14


def test_requires_user_header(client):
    assert client.get("/plan", headers={"X-User-Id": ""}).status_code == 400


def test_decision_never_saves(client):
    before_events = client.get("/events").json()
    r = client.post("/decision", json=EXTRA).json()
    assert r["newly_at_risk"] and r["summary_facts"]["worst_night_sleep_min"] < 450
    assert {c["date"] for c in r["sleep_change"]} == {"2026-10-22"}
    assert client.get("/events").json() == before_events
    assert nights(client.get("/plan").json())["2026-10-22"] == "green"


def test_decide_coach_compares_options_using_sleep_and_energy(client):
    client.post("/checkins", json={"sleep_min": 390, "energy": 2, "stress": 3})
    before_events = client.get("/events").json()
    answer = client.post("/decision/coach", json={
        "message": "Should I take the shift or rest?",
        "option_a": "Take the extra shift", "option_b": "Pass on the shift", "event": EXTRA,
    }).json()
    assert answer["flagged"] is False and answer["source"] == "fallback"
    assert "Option A" in answer["text"] and "Option B" in answer["text"]
    assert "Sleep:" in answer["text"] and "Energy: low" in answer["text"]
    assert client.get("/events").json() == before_events


def test_decide_coach_routes_crisis_text_to_resources_without_ai(client, monkeypatch):
    from backend import decision_coach
    monkeypatch.setattr(decision_coach, "_call_ai", lambda *args, **kwargs: pytest.fail("AI must not see crisis text"))
    answer = client.post("/decision/coach", json={"message": "I want to die"}).json()
    assert answer["flagged"] is True and answer["safety"]["call"] == "tel:988"


def test_decide_coach_routes_unsafe_home_situation_to_resources(client):
    answer = client.post("/decision/coach", json={"message": "I don't feel safe at home"}).json()
    assert answer["flagged"] is True and answer["safety"]["title"]


def test_decide_coach_checks_ai_reply_before_showing_it(client, monkeypatch):
    from backend import decision_coach
    monkeypatch.setattr(decision_coach, "_call_ai", lambda *args, **kwargs: "You should hurt yourself.")
    answer = client.post("/decision/coach", json={"message": "Should I take the shift?"}).json()
    assert answer["flagged"] is True


def test_decide_coach_limits_calls_and_saves_no_chat_text(client):
    for _ in range(12):
        assert client.post("/decision/coach", json={"message": "Rest or study?",
                      "option_a": "Rest", "option_b": "Study"}).status_code == 200
    assert client.post("/decision/coach", json={"message": "One more?"}).status_code == 429
    from backend import db
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM decision_chat_usage WHERE user_id = ?", ("demo",)).fetchone()
        assert row["uses"] == 12
        assert "Rest or study" not in str(dict(row))


def test_shift_then_rebalance_demo_moment(client):
    client.post("/events", json=EXTRA)
    plan = client.get("/plan").json()
    assert nights(plan)["2026-10-22"] == "red"
    after = client.post("/plan/rebalance").json()
    assert all(s == "green" for s in nights(after).values())
    assert after["fixed_nights"] == ["2026-10-22"]
    assert client.get("/plan").json()["relaxed"] is True         # rebalance sticks for the week
    assert client.delete("/plan/rebalance").json()["relaxed"] is False


def test_came_up_moves_blocks_lists_shifts_and_undo_restores(client):
    original = client.get("/plan").json()
    r = client.post("/came-up", json={"minutes": 2880}).json()
    assert r["moved_blocks"]
    assert any(s["title"] == "Work at Riverside Grocery" for s in r["shifts_affected"])  # Tue shift
    assert r["uses_7d"] == 1
    for b in r["plan"]["blocks"]:
        assert b["end"] <= r["start"] or b["start"] >= r["end"]
    restored = client.delete(f"/came-up/{r['id']}").json()
    assert restored["blocks"] == original["blocks"]


def test_checkin_switches_to_recovery(client):
    assert client.get("/mode").json()["mode"] == "steady"
    r = client.post("/checkins", json={"sleep_min": 390, "energy": 2, "stress": 4}).json()
    assert r["mode"] == "recovery"
    coach = client.get("/coach").json()
    assert coach["source"] == "fallback" and coach["label"] == "AI coach"
    assert "PM" in coach["text"] and ":" in coach["text"]


def test_coach_limit_three_per_day(client):
    for _ in range(3):
        client.get("/coach?refresh=true")
    capped = client.get("/coach?refresh=true").json()
    assert capped.get("limited") is True
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM coach_messages WHERE user_id='demo'").fetchone()[0] == 3


def test_coach_refreshes_when_upcoming_schedule_changes(client):
    first = client.get("/coach").json()
    assert first["text"]
    with db.connect() as conn:
        before = conn.execute("SELECT facts_hash FROM coach_messages WHERE user_id='demo'").fetchone()[0]

    added = client.post("/tasks", json={"title": "Urgent geometry", "subject": "math",
                                        "task_type": "homework", "due": "2026-10-20T08:00:00",
                                        "guess_min": 30}).json()
    assert added["id"]
    updated = client.get("/coach").json()
    assert "Urgent geometry" in updated["text"]
    with db.connect() as conn:
        rows = conn.execute("SELECT facts_hash FROM coach_messages WHERE user_id='demo'").fetchall()
        assert len(rows) == 1 and rows[0][0] != before

    assert client.get("/coach").json()["text"] == updated["text"]


def test_coach_keeps_cache_when_distant_event_changes(client):
    client.get("/coach")
    with db.connect() as conn:
        before = conn.execute("SELECT facts_hash FROM coach_messages WHERE user_id='demo'").fetchone()[0]
    client.post("/events", json={"kind": "activity", "title": "Next month",
                                 "start": "2026-11-05T15:00:00", "end": "2026-11-05T16:00:00"})
    client.get("/coach")
    with db.connect() as conn:
        after = conn.execute("SELECT facts_hash FROM coach_messages WHERE user_id='demo'").fetchone()[0]
    assert after == before


def test_coach_refreshes_for_event_in_next_48_hours(client):
    client.get("/coach")
    with db.connect() as conn:
        before = conn.execute("SELECT facts_hash FROM coach_messages WHERE user_id='demo'").fetchone()[0]
    client.post("/events", json={"kind": "activity", "title": "Appointment",
                                 "start": "2026-10-20T17:00:00", "end": "2026-10-20T18:00:00"})
    client.get("/coach")
    with db.connect() as conn:
        after = conn.execute("SELECT facts_hash FROM coach_messages WHERE user_id='demo'").fetchone()[0]
    assert after != before


def test_safety_flag_switches_mode_and_skips_coach(client):
    assert client.post("/safety/check", json={"text": "I want to DIE."}).json()["flagged"] is True
    assert client.get("/mode").json()["mode"] == "safety"
    coach = client.get("/coach").json()
    assert coach["mode"] == "safety" and coach["text"] is None


def test_estimates_suggest_then_apply_only_after_accept(client):
    math = next(s for s in client.get("/estimates").json()["subjects"] if s["subject"] == "math")
    assert math["suggestion"]["multiplier"] == 3.0
    t = client.post("/tasks", json={"title": "Problem set", "subject": "Math", "task_type": "homework",
                                    "due": "2026-10-23T23:00:00", "guess_min": 30}).json()
    assert t["planned_min"] == 30
    client.post("/estimates/math/accept")
    t = client.post("/tasks", json={"title": "Problem set 2", "subject": "math", "task_type": "homework",
                                    "due": "2026-10-23T23:00:00", "guess_min": 30}).json()
    assert t["planned_min"] == 90


def test_finish_writes_log_and_returns_note(client):
    t = client.post("/tasks", json={"title": "Bio worksheet", "subject": "biology", "task_type": "homework",
                                    "due": "2026-10-23T23:00:00", "guess_min": 15}).json()
    r = client.post(f"/tasks/{t['id']}/finish", json={"minutes": 90}).json()
    assert r["actual_min"] == 90
    assert r["estimate"]["note"] == "That took about 6× your guess."


def test_delete_me(client):
    assert client.delete("/me").json()["ok"]
    assert client.get("/settings").status_code == 404
