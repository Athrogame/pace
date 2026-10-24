"""Repeatable demo data for a short app walkthrough.

    python -m backend.seed_demo            # seeds user "demo" for the current week
    then open http://localhost:8000/?as=demo

For a recording, pin the demo plan's clock to Monday afternoon so the week looks the same every
take. Only the demo plan is pinned; everyone else keeps the real date:
    PACE_DEMO_NOW=2026-10-19T15:30:00  (PowerShell: $env:PACE_DEMO_NOW="2026-10-19T15:30:00")

Demo script that this data is tuned for (Monday 3:30 PM, all nights green to start):
  1. Something came up -> "The rest of today" -> tonight's study moves, Thursday night turns red,
     History essay + Math test study flagged at risk ("Consider asking your teacher for an extension").
  2. Week -> Rebalance my week -> every night green again (earlier/later days absorb the work).
  3. Decide: "Extra shift" Wednesday 3:15 PM to 9:30 PM -> before/after shows the nights it would
     cost and the tasks that stop fitting -> "Not this time". Nothing is saved.
  4. Check in: 6 hr 30 min of sleep, energy 2, stress 4 -> coach switches to Recovery.
The extra shift is on Wednesday because Thursday already has a regular shift.
Re-run this script to reset the demo between takes.
"""
import json
import sys
from datetime import date, datetime, timedelta

from . import db
from .timeutil import iso, local_now

DEMO_USER = "demo"


def week_monday(today: date) -> date:
    return today - timedelta(days=today.weekday())


def seed(user_id: str = DEMO_USER, today: date = None) -> dict:
    db.init_db()
    today = today or local_now(user_id=user_id).date()
    mon = week_monday(today)
    day = lambda n, hm: f"{(mon + timedelta(days=n)).isoformat()}T{hm}:00"  # noqa: E731
    created = iso(datetime.combine(mon - timedelta(days=7), datetime.min.time()))

    with db.connect() as conn:
        db.delete_user(conn, user_id)
        weekdays = {k: "06:45" for k in ["mon", "tue", "wed", "thu", "fri"]}
        conn.execute(
            """INSERT INTO settings (user_id, nickname, timezone, sleep_goal_min, wake_times, school_blocks,
                   commute_min, max_study_school_night_min, max_study_weekend_day_min, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (user_id, "Jordan", "America/New_York", 510,
             json.dumps({**weekdays, "sat": "09:00", "sun": "09:00"}),
             json.dumps({**{k: ["07:45", "14:45"] for k in weekdays}, "sat": None, "sun": None}),
             20, 90, 240, created))

        # Recurring shifts: Tue + Thu 5-9 PM, Sat 10 AM-4 PM. They started last week.
        prev = mon - timedelta(days=7)
        for days, start, end in [(["tue", "thu"], "17:00", "21:00"), (["sat"], "10:00", "16:00")]:
            conn.execute('INSERT INTO events (user_id, kind, title, start, "end", recurring) VALUES (?,?,?,?,?,?)',
                         (user_id, "shift", "Work at Riverside Grocery", f"{prev.isoformat()}T{start}:00",
                          f"{prev.isoformat()}T{end}:00", json.dumps({"days": days})))

        tasks = [
            ("English reading: ch. 7-8", "english", "homework", day(2, "08:00"), 45, 45),
            ("Chem lab report", "chemistry", "homework", day(3, "08:00"), 90, 90),
            ("History essay", "history", "essay", day(4, "08:00"), 180, 180),
            ("Math test study", "math", "test_study", day(4, "08:00"), 30, 30),
        ]
        for title, subject, ttype, due, guess, planned in tasks:
            conn.execute("""INSERT INTO tasks (user_id, title, subject, task_type, due, guess_min, planned_min, created_at)
                            VALUES (?,?,?,?,?,?,?,?)""", (user_id, title, subject, ttype, due, guess, planned, created))

        # Three finished math tasks from last week, each about 3x the guess -> estimate suggestion.
        for i, (guess, actual) in enumerate([(20, 60), (30, 95), (40, 115)]):
            when = iso(datetime.combine(prev + timedelta(days=i), datetime.min.time()) + timedelta(hours=20))
            cur = conn.execute("""INSERT INTO tasks (user_id, title, subject, task_type, due, guess_min, planned_min,
                                      done_min, completed, created_at) VALUES (?,?,?,?,?,?,?,?,1,?)""",
                               (user_id, f"Math worksheet {i + 1}", "math", "homework", when, guess, guess, actual, created))
            conn.execute("""INSERT INTO work_logs (user_id, task_id, subject, guess_min, actual_min, logged_at)
                            VALUES (?,?,?,?,?,?)""", (user_id, cur.lastrowid, "math", guess, actual, when))

        # Two short-ish nights (75 min under goal each = 150 min debt, just under the 180 Recovery line).
        # Today's check-in is left empty: a bad one in the demo tips it into Recovery.
        for back in (2, 1):
            d = (today - timedelta(days=back)).isoformat()
            conn.execute("INSERT INTO checkins (user_id, date, sleep_min, energy, stress) VALUES (?,?,?,?,?)",
                         (user_id, d, 435, 3, 3))
    return {"user_id": user_id, "monday": mon.isoformat()}


if __name__ == "__main__":
    out = seed(sys.argv[1] if len(sys.argv) > 1 else DEMO_USER)
    print(f"Seeded demo user '{out['user_id']}' for the week of {out['monday']}.")
    print("Open http://localhost:8000/?as=demo")
