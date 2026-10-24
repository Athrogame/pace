"""Copy an existing local Pace SQLite database to an empty PostgreSQL database.

Usage after setting PACE_DATABASE_URL in .env:
    python -m backend.migrate_to_postgres path/to/pace.db

The source file is never changed. The target must be empty, preventing an accidental merge
of different users. No records or credentials are printed.
"""
import os
import sqlite3
import sys
from pathlib import Path

from dotenv import load_dotenv

from . import db

TABLES = db.USER_TABLES
ID_TABLES = {"events", "tasks", "work_logs", "checkins", "blocked_times",
             "coach_messages", "safety_flags"}


def migrate(source_path: str) -> dict:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    if not os.environ.get("PACE_DATABASE_URL"):
        raise RuntimeError("Set PACE_DATABASE_URL in .env before migrating")
    source = Path(source_path).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    db.init_db()
    counts = {}
    with sqlite3.connect(source) as old, db.connect() as new:
        old.row_factory = sqlite3.Row
        existing = sum(new.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"] for table in TABLES)
        if existing:
            raise RuntimeError("The PostgreSQL target already has Pace data; use an empty project")
        for table in TABLES:
            if not old.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
                counts[table] = 0
                continue
            rows = old.execute(f"SELECT * FROM {table}").fetchall()
            if not rows:
                counts[table] = 0
                continue
            available = {row["column_name"] for row in new.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'pace' AND table_name = ?", (table,)).fetchall()}
            columns = [name for name in rows[0].keys() if name in available]
            names = ", ".join('"' + name.replace('"', '""') + '"' for name in columns)
            placeholders = ", ".join("?" for _ in columns)
            statement = f"INSERT INTO {table} ({names}) VALUES ({placeholders})"
            new.executemany(statement, [tuple(row[name] for name in columns) for row in rows])
            counts[table] = len(rows)
        for table in ID_TABLES:
            new.execute(
                f"SELECT setval(pg_get_serial_sequence('pace.{table}', 'id'), "
                f"GREATEST((SELECT COALESCE(MAX(id), 0) FROM {table}), 1), "
                f"(SELECT COUNT(*) > 0 FROM {table}))")
    return counts


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python -m backend.migrate_to_postgres PATH_TO_SQLITE_DB")
    copied = migrate(sys.argv[1])
    print("Copied " + ", ".join(f"{count} {table}" for table, count in copied.items() if count))
