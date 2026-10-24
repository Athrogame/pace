"""Google Calendar import: read-only events become busy time; re-import replaces, never duplicates."""
import pytest
from fastapi.testclient import TestClient

from backend import db

NOW = "2026-10-19T15:30:00"   # Monday afternoon


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "cal.db"))
    monkeypatch.setenv("PACE_NOW", NOW)
    from backend.main import app
    from backend.seed_demo import seed
    from datetime import date
    db.init_db()
    seed("demo", date(2026, 10, 19))
    seed("student-1", date(2026, 10, 19))   # a student's own plan (same week, not the shared demo)
    with TestClient(app) as c:
        c.headers["X-User-Id"] = "student-1"
        yield c


def test_shared_demo_never_gets_a_real_calendar(client):
    r = client.post("/calendar/import", headers={"X-User-Id": "demo"},
                    json={"events": [ev("Dentist", "2026-10-19T16:00:00", "2026-10-19T17:00:00")]})
    assert r.status_code == 409 and "demo" in r.json()["detail"]
    demo_events = client.get("/events", headers={"X-User-Id": "demo"}).json()
    assert not any(e.get("source") == "google" for e in demo_events)


def ev(title, start, end):
    return {"title": title, "start": start, "end": end}


def imported(client):
    return [e for e in client.get("/events").json() if e.get("source") == "google"]


def test_import_blocks_time_and_replaces_on_reimport(client):
    r = client.post("/calendar/import", json={"events": [
        ev("Dentist", "2026-10-19T16:00:00", "2026-10-19T17:00:00"),
        ev("Youth group", "2026-10-21T18:00:00", "2026-10-21T19:30:00"),
    ]}).json()
    assert r["imported"] == 2 and r["skipped"] == 0
    plan = client.get("/plan").json()
    for b in plan["blocks"]:                      # nothing planned during the dentist visit
        assert b["end"] <= "2026-10-19T16:00:00" or b["start"] >= "2026-10-19T17:00:00"
    monday = next(d for d in plan["days"] if d["date"] == "2026-10-19")
    assert any(e["title"] == "Dentist" and e["source"] == "google" for e in monday["events"])

    client.post("/calendar/import", json={"events": [ev("Dentist", "2026-10-19T16:00:00", "2026-10-19T17:00:00")]})
    assert [e["title"] for e in imported(client)] == ["Dentist"]          # replaced, not duplicated
    assert client.get("/calendar/status").json()["imported"] == 1


def test_imported_events_are_not_work(client):
    before = client.get("/plan").json()["work_hours_this_week"]
    client.post("/calendar/import", json={"events": [ev("Shift swap?", "2026-10-22T10:00:00", "2026-10-22T14:00:00")]})
    assert client.get("/plan").json()["work_hours_this_week"] == before
    assert imported(client)[0]["kind"] == "activity"


def test_skips_past_too_long_and_broken_events(client):
    r = client.post("/calendar/import", json={"events": [
        ev("Yesterday", "2026-10-18T10:00:00", "2026-10-18T11:00:00"),
        ev("Trip", "2026-10-20T08:00:00", "2026-10-22T08:00:00"),
        ev("Backwards", "2026-10-20T12:00:00", "2026-10-20T11:00:00"),
        ev("Not a time", "soon", "later"),
        ev("Club", "2026-10-20T15:30:00", "2026-10-20T16:30:00"),
    ]}).json()
    assert r == {"imported": 1, "skipped": 4, "synced_at": "2026-10-19T15:30:00"}


def test_flagged_titles_become_busy_and_pace_events_survive(client):
    pace_events = len([e for e in client.get("/events").json() if not e.get("source")])
    client.post("/calendar/import", json={"events": [ev("I want to die", "2026-10-20T15:30:00", "2026-10-20T16:00:00")]})
    assert imported(client)[0]["title"] == "Busy"
    assert client.get("/mode").json()["mode"] != "safety"   # not something they typed into Pace
    client.delete("/calendar/import")
    assert imported(client) == []
    assert len(client.get("/events").json()) == pace_events  # Pace's own shifts untouched
    assert client.get("/calendar/status").json() == {"imported": 0, "synced_at": None}


def test_migration_adds_columns_to_an_old_database(tmp_path, monkeypatch):
    import sqlite3
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.executescript("CREATE TABLE events (id INTEGER PRIMARY KEY, user_id TEXT, kind TEXT, title TEXT,"
                      " start TEXT, end TEXT, recurring TEXT);"
                      "CREATE TABLE tasks (id INTEGER PRIMARY KEY, user_id TEXT, title TEXT);")
    old.close()
    monkeypatch.setattr(db, "DB_PATH", str(path))
    db.init_db()
    cols = {r[1] for r in sqlite3.connect(path).execute("PRAGMA table_info(events)")}
    assert "source" in cols
    task_cols = {r[1] for r in sqlite3.connect(path).execute("PRAGMA table_info(tasks)")}
    assert {"source", "external_id"} <= task_cols


def google_task(external_id="list-1:task-1", title="Science worksheet", due="2026-10-21T20:00:00"):
    return {"external_id": external_id, "title": title, "subject": "science",
            "due": due, "guess_min": 45}


def test_google_tasks_import_is_read_only_copy_and_deduplicates(client):
    body = {"tasks": [{**google_task(), "task_type": "test_study"}]}
    first = client.post("/tasks/google/import", json=body)
    assert first.status_code == 200 and first.json() == {"imported": 1, "already_here": 0, "skipped": 0}
    task = next(t for t in client.get("/tasks").json() if t.get("source") == "google_tasks")
    assert task["title"] == "Science worksheet" and task["external_id"] == "list-1:task-1"
    assert task["planned_min"] == 45
    assert task["task_type"] == "test_study"
    client.post(f"/tasks/{task['id']}/log", json={"minutes": 15})
    again = client.post("/tasks/google/import", json=body).json()
    assert again == {"imported": 0, "already_here": 1, "skipped": 0}
    assert next(t for t in client.get("/tasks").json() if t["id"] == task["id"])["done_min"] == 15


def test_google_tasks_import_skips_invalid_and_cannot_write_demo(client):
    tasks = [google_task("old", due="2026-10-18T20:00:00"),
             google_task("unsafe", title="I want to die"), google_task("bad", due="not-a-date")]
    assert client.post("/tasks/google/import", json={"tasks": tasks}).json() == {
        "imported": 0, "already_here": 0, "skipped": 3}
    denied = client.post("/tasks/google/import", headers={"X-User-Id": "demo"},
                         json={"tasks": [google_task()]})
    assert denied.status_code == 409
    assert not any(t.get("source") == "google_tasks" for t in client.get("/tasks").json())
