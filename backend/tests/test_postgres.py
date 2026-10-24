"""PostgreSQL adapter preserves the queries used by Pace's SQLite code."""
import pytest

from backend import db, postgres


def test_rows_support_name_and_position():
    row = postgres.HybridRow([("n", 3), ("title", "Essay")])
    assert row["n"] == row[0] == 3
    assert row["title"] == row[1] == "Essay"


def test_insert_translation_preserves_ids_and_conflicts():
    sql, returning = postgres._translate("INSERT INTO tasks (user_id, title) VALUES (?, ?)")
    assert sql.endswith("RETURNING id") and "%s" in sql and returning
    ignored, returning = postgres._translate("INSERT OR IGNORE INTO tasks (user_id) VALUES (?)")
    assert "ON CONFLICT DO NOTHING RETURNING id" in ignored and returning
    upsert, returning = postgres._translate(
        "INSERT INTO checkins (user_id, date) VALUES (?, ?) "
        "ON CONFLICT(user_id, date) DO UPDATE SET date=excluded.date")
    assert upsert.endswith("RETURNING id") and returning
    bulk, returning = postgres._translate("INSERT INTO events (user_id) VALUES (?)", many=True)
    assert "RETURNING" not in bulk and not returning


def test_durable_deploy_refuses_ephemeral_sqlite(monkeypatch):
    monkeypatch.setenv("PACE_REQUIRE_DURABLE_DB", "1")
    monkeypatch.delenv("PACE_DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="PACE_DATABASE_URL"):
        db.init_db()


def test_schema_comments_do_not_become_postgres_statements():
    class Raw:
        def __init__(self):
            self.statements = []

        def execute(self, statement):
            self.statements.append(statement.strip())

    raw = Raw()
    postgres.Connection(raw).executescript(db.SCHEMA)
    assert raw.statements
    assert all(statement.startswith("CREATE TABLE") for statement in raw.statements)
    assert not any("--" in statement for statement in raw.statements)
