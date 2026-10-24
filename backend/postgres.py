"""Small compatibility layer for Pace's SQLite-style queries on PostgreSQL.

All application tables live in the private ``pace`` schema, outside Supabase's
default public Data API schema. Only the server receives the connection URL.
"""
import re


class HybridRow(dict):
    """Support both row['column'] and row[0], as SQLite rows do in this app."""

    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


def _row_factory(cursor):
    names = [column.name for column in (cursor.description or [])]
    return lambda values: HybridRow(zip(names, values))


ID_TABLES = {"events", "tasks", "work_logs", "checkins", "blocked_times",
             "coach_messages", "safety_flags"}


def _translate(query, *, many=False):
    """Adapt the small set of SQLite constructs used by Pace's existing queries."""
    sql = query.replace("?", "%s")
    ignored = bool(re.match(r"\s*INSERT\s+OR\s+IGNORE\s+INTO\s+", sql, re.I))
    if ignored:
        sql = re.sub(r"\bINSERT\s+OR\s+IGNORE\s+INTO\b", "INSERT INTO", sql, count=1, flags=re.I)
        sql = sql.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
    match = re.match(r"\s*INSERT\s+INTO\s+(\w+)\b", sql, re.I)
    returning = bool(match and match.group(1).lower() in ID_TABLES and not many)
    if returning:
        # The API expects cursor.lastrowid after these inserts. PostgreSQL needs
        # an explicit RETURNING clause, which the wrapper consumes below.
        sql = sql.rstrip().rstrip(";") + " RETURNING id"
    return sql, returning


class Cursor:
    def __init__(self, raw, lastrowid=None):
        self.raw = raw
        self.lastrowid = lastrowid

    @property
    def rowcount(self):
        return self.raw.rowcount

    def fetchone(self):
        return self.raw.fetchone()

    def fetchall(self):
        return self.raw.fetchall()


class Connection:
    def __init__(self, raw):
        self.raw = raw

    def __enter__(self):
        self.raw.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb):
        return self.raw.__exit__(exc_type, exc, tb)

    def execute(self, query, params=()):
        sql, returning = _translate(query)
        cursor = self.raw.execute(sql, params)
        lastrowid = None
        if returning:
            row = cursor.fetchone()
            lastrowid = row["id"] if row else None
        return Cursor(cursor, lastrowid)

    def executemany(self, query, params):
        sql, _ = _translate(query, many=True)
        cursor = self.raw.cursor()
        cursor.executemany(sql, params)
        return Cursor(cursor)

    def executescript(self, script):
        # Strip SQLite schema comments first; some contain semicolons that are
        # not SQL statement boundaries.
        script = re.sub(r"(?m)^\s*--[^\n]*$", "", script)
        for statement in script.split(";"):
            if statement.strip():
                self.raw.execute(statement)

    def commit(self):
        self.raw.commit()

    def close(self):
        self.raw.close()


def connect(url):
    import psycopg

    raw = psycopg.connect(url, row_factory=_row_factory, sslmode="require",
                          prepare_threshold=None, connect_timeout=8)
    raw.execute("SET search_path TO pace, public")
    return Connection(raw)
