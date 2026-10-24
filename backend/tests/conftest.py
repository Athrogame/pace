import copy
from datetime import datetime

import pytest

# Monday Oct 19 2026, 3:30 PM. School ends 2:45 PM, so the afternoon is free.
NOW = datetime(2026, 10, 19, 15, 30)

SETTINGS = {
    "timezone": "America/New_York",
    "sleep_goal_min": 510,
    "wake_times": {"mon": "06:45", "tue": "06:45", "wed": "06:45", "thu": "06:45",
                   "fri": "06:45", "sat": "09:00", "sun": "09:00"},
    "school_blocks": {"mon": ["07:45", "14:45"], "tue": ["07:45", "14:45"], "wed": ["07:45", "14:45"],
                      "thu": ["07:45", "14:45"], "fri": ["07:45", "14:45"], "sat": None, "sun": None},
    "commute_min": 20,
    "max_study_school_night_min": 120,
    "max_study_weekend_day_min": 240,
}


@pytest.fixture(autouse=True)
def keep_tests_on_sqlite(monkeypatch):
    # Never let a developer's .env point tests at their real Supabase database.
    monkeypatch.setenv("PACE_USE_SQLITE", "1")


@pytest.fixture
def settings():
    return copy.deepcopy(SETTINGS)


def task(id, title, due, minutes, subject="math", done=0):
    return {"id": id, "title": title, "subject": subject, "due": due,
            "planned_min": minutes, "guess_min": minutes, "done_min": done, "completed": 0}


def shift(id, start, end, recurring=None, title="Shift"):
    return {"id": id, "kind": "shift", "title": title, "start": start, "end": end, "recurring": recurring}
