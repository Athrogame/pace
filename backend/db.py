"""SQLite connection, schema, and small load helpers."""
import json
import os
import sqlite3
from pathlib import Path

DB_PATH = os.environ.get("PACE_DB", str(Path(__file__).resolve().parent.parent / "pace.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
  user_id          TEXT PRIMARY KEY,
  nickname         TEXT,
  timezone         TEXT NOT NULL DEFAULT 'America/New_York',
  sleep_goal_min   INTEGER NOT NULL DEFAULT 510,
  wake_times       TEXT NOT NULL,
  school_blocks    TEXT NOT NULL,
  commute_min      INTEGER NOT NULL DEFAULT 20,
  max_study_school_night_min INTEGER NOT NULL DEFAULT 120,
  max_study_weekend_day_min  INTEGER NOT NULL DEFAULT 240,
  relaxed_until    TEXT,
  created_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id     TEXT NOT NULL,
  kind        TEXT NOT NULL CHECK (kind IN ('shift','activity')),
  title       TEXT NOT NULL,
  start       TEXT NOT NULL,
  "end"       TEXT NOT NULL,
  recurring   TEXT
);

CREATE TABLE IF NOT EXISTS tasks (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id          TEXT NOT NULL,
  title            TEXT NOT NULL,
  subject          TEXT NOT NULL,
  task_type        TEXT NOT NULL,
  due              TEXT NOT NULL,
  guess_min        INTEGER NOT NULL,
  planned_min      INTEGER NOT NULL,
  done_min         INTEGER NOT NULL DEFAULT 0,
  completed        INTEGER NOT NULL DEFAULT 0,
  created_at       TEXT NOT NULL,
  source           TEXT,
  external_id      TEXT
);

CREATE TABLE IF NOT EXISTS work_logs (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id     TEXT NOT NULL,
  task_id     INTEGER NOT NULL,
  subject     TEXT NOT NULL,
  guess_min   INTEGER NOT NULL,
  actual_min  INTEGER NOT NULL,
  logged_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS checkins (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id     TEXT NOT NULL,
  date        TEXT NOT NULL,
  sleep_min   INTEGER,
  energy      INTEGER CHECK (energy BETWEEN 1 AND 5),
  stress      INTEGER CHECK (stress BETWEEN 1 AND 5),
  UNIQUE (user_id, date)
);

CREATE TABLE IF NOT EXISTS blocked_times (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id     TEXT NOT NULL,
  start       TEXT NOT NULL,
  "end"       TEXT NOT NULL,
  created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS estimate_prefs (
  user_id     TEXT NOT NULL,
  subject     TEXT NOT NULL,
  multiplier  REAL NOT NULL,
  accepted_at TEXT NOT NULL,
  PRIMARY KEY (user_id, subject)
);

CREATE TABLE IF NOT EXISTS coach_messages (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id     TEXT NOT NULL,
  mode        TEXT NOT NULL,
  text        TEXT NOT NULL,
  source      TEXT NOT NULL CHECK (source IN ('ai','fallback','safety')),
  sent_at     TEXT NOT NULL,
  facts_hash  TEXT
);

-- Only a daily request count is kept for Decide chat; chat text is not saved.
CREATE TABLE IF NOT EXISTS decision_chat_usage (
  user_id     TEXT NOT NULL,
  date        TEXT NOT NULL,
  uses        INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (user_id, date)
);

-- The safety marker expires from consideration after 24 hours.
CREATE TABLE IF NOT EXISTS safety_flags (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id     TEXT NOT NULL,
  flagged_at  TEXT NOT NULL
);

-- Optional accounts. No email or real name: a username the student picks, and a password hash.
CREATE TABLE IF NOT EXISTS accounts (
  user_id        TEXT PRIMARY KEY,
  username       TEXT NOT NULL UNIQUE,
  password_hash  TEXT NOT NULL,
  created_at     TEXT NOT NULL
);

-- Sign in with Google. Only Google's stable account number ("sub") is kept: no email, no name.
CREATE TABLE IF NOT EXISTS google_accounts (
  google_sub  TEXT PRIMARY KEY,
  user_id     TEXT NOT NULL UNIQUE,
  created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
  token_hash  TEXT PRIMARY KEY,
  user_id     TEXT NOT NULL,
  created_at  INTEGER NOT NULL,
  expires_at  INTEGER NOT NULL
);

-- Pending rows contain only a parent contact address until consent is complete.
CREATE TABLE IF NOT EXISTS parent_email_consents (
  user_id                 TEXT PRIMARY KEY,
  parent_email            TEXT NOT NULL,
  request_token_hash      TEXT NOT NULL UNIQUE,
  confirm_token_hash      TEXT,
  requested_at            INTEGER NOT NULL,
  accepted_at             INTEGER,
  confirmation_sent_at    INTEGER,
  confirmed_at            INTEGER,
  revoked_at              INTEGER
);

-- Short-lived, shared counters for abuse prevention. Keys are HMACs, not raw IPs.
CREATE TABLE IF NOT EXISTS rate_limits (
  bucket       TEXT NOT NULL,
  window_start INTEGER NOT NULL,
  hits         INTEGER NOT NULL,
  PRIMARY KEY (bucket, window_start)
);
"""

USER_TABLES = ["settings", "events", "tasks", "work_logs", "checkins", "blocked_times",
               "estimate_prefs", "coach_messages", "decision_chat_usage", "safety_flags", "accounts", "google_accounts", "sessions",
               "parent_email_consents"]


def connect():
    url = os.environ.get("PACE_DATABASE_URL")
    if url and os.environ.get("PACE_USE_SQLITE") != "1":
        from . import postgres
        return postgres.connect(url)
    # One connection per request, but FastAPI may open it and use it on different worker threads.
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


# Columns added after the first release. init_db adds any that an older pace.db is missing.
MIGRATIONS = [
    ("events", "source", "TEXT"),                  # NULL = added in Pace, 'google' = imported
    ("settings", "calendar_synced_at", "TEXT"),    # last Google Calendar import
    ("tasks", "source", "TEXT"),                    # NULL = added in Pace
    ("tasks", "external_id", "TEXT"),               # Google Tasks list ID + task ID
    ("coach_messages", "facts_hash", "TEXT"),       # schedule used to write this message
]


def init_db() -> None:
    postgres_mode = bool(os.environ.get("PACE_DATABASE_URL") and os.environ.get("PACE_USE_SQLITE") != "1")
    if os.environ.get("PACE_REQUIRE_DURABLE_DB") == "1" and not postgres_mode:
        # Render's local filesystem is ephemeral; fail startup rather than lose plans.
        raise RuntimeError("PACE_DATABASE_URL is required for durable deployment storage")
    with connect() as conn:
        if postgres_mode:
            conn.execute("CREATE SCHEMA IF NOT EXISTS pace")
            conn.executescript(SCHEMA.replace("INTEGER PRIMARY KEY AUTOINCREMENT",
                                              "BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY"))
            for table, column, kind in MIGRATIONS:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {kind}")
        else:
            conn.executescript(SCHEMA)
            for table, column, kind in MIGRATIONS:
                have = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
                if column not in have:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {kind}")
        conn.execute("""CREATE UNIQUE INDEX IF NOT EXISTS tasks_external_unique
                        ON tasks(user_id, source, external_id)
                        WHERE source IS NOT NULL AND external_id IS NOT NULL""")


def row_to_dict(row) -> dict:
    return dict(row) if row is not None else None


def load_settings(conn, user_id: str):
    row = conn.execute("SELECT * FROM settings WHERE user_id = ?", (user_id,)).fetchone()
    if row is None:
        return None
    s = dict(row)
    s["wake_times"] = json.loads(s["wake_times"])
    s["school_blocks"] = json.loads(s["school_blocks"])
    return s


def load_events(conn, user_id: str) -> list:
    rows = conn.execute("SELECT * FROM events WHERE user_id = ? ORDER BY start", (user_id,)).fetchall()
    out = []
    for r in rows:
        e = dict(r)
        e["recurring"] = json.loads(e["recurring"]) if e["recurring"] else None
        out.append(e)
    return out


def load_tasks(conn, user_id: str, include_completed: bool = False) -> list:
    sql = "SELECT * FROM tasks WHERE user_id = ?"
    if not include_completed:
        sql += " AND completed = 0"
    return [dict(r) for r in conn.execute(sql + " ORDER BY due", (user_id,)).fetchall()]


def load_blocked(conn, user_id: str) -> list:
    rows = conn.execute("SELECT * FROM blocked_times WHERE user_id = ? ORDER BY start", (user_id,)).fetchall()
    return [dict(r) for r in rows]


def load_checkins(conn, user_id: str, since_date: str) -> list:
    rows = conn.execute(
        "SELECT * FROM checkins WHERE user_id = ? AND date >= ? ORDER BY date",
        (user_id, since_date),
    ).fetchall()
    return [dict(r) for r in rows]


def load_logs(conn, user_id: str, subject: str = None) -> list:
    """Newest first."""
    if subject:
        rows = conn.execute(
            "SELECT * FROM work_logs WHERE user_id = ? AND subject = ? ORDER BY logged_at DESC, id DESC",
            (user_id, subject),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM work_logs WHERE user_id = ? ORDER BY logged_at DESC, id DESC", (user_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def load_prefs(conn, user_id: str) -> dict:
    rows = conn.execute("SELECT subject, multiplier FROM estimate_prefs WHERE user_id = ?", (user_id,)).fetchall()
    return {r["subject"]: r["multiplier"] for r in rows}


def delete_user(conn, user_id: str) -> None:
    for table in USER_TABLES:
        conn.execute(f"DELETE FROM {table} WHERE user_id = ?", (user_id,))
