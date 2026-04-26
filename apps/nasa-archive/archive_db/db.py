"""
db.py -- Database connection abstraction for nasa-archive.

PostgreSQL-only. All data lives in Postgres under schema nasa_archive.
Requires WILLOW_DB_URL=postgresql://... in the environment.
All code calls get_connection() -- never sqlite3.connect() directly.

Mirrors /mnt/c/Users/Sean/Documents/GitHub/Willow/core/db.py pattern.
"""
import os
import threading

DATABASE_URL = os.getenv("WILLOW_DB_URL", "")
if not DATABASE_URL:
    raise RuntimeError(
        "WILLOW_DB_URL is not set. "
        "Set it to postgresql://willow:willow@172.26.176.1:5437/willow"
    )

SCHEMA = "nasa_archive"

_pg_pool      = None
_pg_pool_lock = threading.Lock()


def _get_pg_pool():
    global _pg_pool
    if _pg_pool is not None:
        return _pg_pool
    with _pg_pool_lock:
        if _pg_pool is None:
            try:
                import psycopg2.pool
                _pg_pool = psycopg2.pool.ThreadedConnectionPool(
                    minconn=2, maxconn=20, dsn=DATABASE_URL
                )
            except ImportError:
                raise RuntimeError(
                    "psycopg2 not installed. Run: pip install psycopg2-binary"
                )
    return _pg_pool


import re as _re

# Conflict targets for INSERT OR REPLACE upserts (table -> ON CONFLICT clause)
_PG_CONFLICT_TARGETS: dict = {
    "oral_events":    "(archive_slug) DO UPDATE SET name=EXCLUDED.name, "
                      "event_year=EXCLUDED.event_year, source_type=EXCLUDED.source_type, "
                      "confidence=EXCLUDED.confidence, sources=EXCLUDED.sources",
    "oral_clubs":     "(name) DO UPDATE SET city=EXCLUDED.city, state=EXCLUDED.state, "
                      "notes=EXCLUDED.notes, source_type=EXCLUDED.source_type, "
                      "confidence=EXCLUDED.confidence, sources=EXCLUDED.sources",
    "oral_persons":   "(club_name) DO UPDATE SET home_city=EXCLUDED.home_city, "
                      "home_state=EXCLUDED.home_state, bio=EXCLUDED.bio, "
                      "source_type=EXCLUDED.source_type, confidence=EXCLUDED.confidence, "
                      "sources=EXCLUDED.sources",
    "oral_locations": "(name) DO UPDATE SET city=EXCLUDED.city, state=EXCLUDED.state, "
                      "location_type=EXCLUDED.location_type, notes=EXCLUDED.notes, "
                      "source_type=EXCLUDED.source_type, confidence=EXCLUDED.confidence, "
                      "sources=EXCLUDED.sources",
    "oral_stories":   "(capture_session) DO UPDATE SET content=EXCLUDED.content, "
                      "summary=EXCLUDED.summary, source_type=EXCLUDED.source_type, "
                      "confidence=EXCLUDED.confidence, sources=EXCLUDED.sources",
}


def _sqlite_to_pg(sql):
    """Translate SQLite SQL syntax to PostgreSQL."""
    s = sql.strip()
    if _re.match(r"\s*PRAGMA\b", s, _re.IGNORECASE):
        return "SELECT 1"
    if _re.search(r"\bINSERT\s+OR\s+IGNORE\b", s, _re.IGNORECASE):
        s = _re.sub(r"\bINSERT\s+OR\s+IGNORE\b", "INSERT", s, flags=_re.IGNORECASE)
        s = s.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
    elif _re.search(r"\bINSERT\s+OR\s+REPLACE\b", s, _re.IGNORECASE):
        s = _re.sub(r"\bINSERT\s+OR\s+REPLACE\b", "INSERT", s, flags=_re.IGNORECASE)
        m = _re.search(r"\bINSERT\s+INTO\s+[\"']?(\w+)", s, _re.IGNORECASE)
        table = m.group(1).lower() if m else ""
        conflict = _PG_CONFLICT_TARGETS.get(table, "DO NOTHING")
        s = s.rstrip().rstrip(";") + f" ON CONFLICT {conflict}"
    # Only translate ? -> %s if query uses SQLite-style placeholders.
    if "?" in s:
        s = s.replace("%", "%%")
        s = s.replace("?", "%s")
    return s


class _PgCursor:
    """Wraps psycopg2 cursor to provide sqlite3-compatible interface."""

    def __init__(self, cur):
        self._cur = cur
        self.description = cur.description
        self.rowcount    = cur.rowcount
        self.lastrowid   = None

    def __getattr__(self, name):
        return getattr(self._cur, name)

    def execute(self, sql, params=None):
        pg_sql = _sqlite_to_pg(sql)
        self._cur.execute(pg_sql, params)
        self.description = self._cur.description
        self.rowcount    = self._cur.rowcount
        if _re.match(r"\s*INSERT\b", pg_sql, _re.IGNORECASE):
            try:
                self._cur.execute("SELECT lastval()")
                row = self._cur.fetchone()
                self.lastrowid = row[0] if row else None
            except Exception:
                self.lastrowid = None
        else:
            self.lastrowid = None
        return self

    def executemany(self, sql, seq):
        import psycopg2.extras
        pg_sql = _sqlite_to_pg(sql)
        psycopg2.extras.execute_batch(self._cur, pg_sql, seq)

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    def fetchmany(self, n):
        return self._cur.fetchmany(n)

    def __iter__(self):
        return iter(self._cur)


class _PgConn:
    """Wraps a pooled psycopg2 connection with sqlite3-compatible interface."""

    def __init__(self, pool, conn):
        self._pool = pool
        self._conn = conn
        self._row_factory = None

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def cursor(self):
        import sqlite3 as _sqlite3
        if self._row_factory is _sqlite3.Row:
            import psycopg2.extras
            return _PgCursor(
                self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            )
        return _PgCursor(self._conn.cursor())

    def execute(self, sql, params=None):
        cur = self.cursor()
        cur.execute(sql, params)
        return cur

    @property
    def row_factory(self):
        return self._row_factory

    @row_factory.setter
    def row_factory(self, value):
        self._row_factory = value

    def close(self):
        try:
            self._conn.rollback()
        except Exception:
            pass
        self._pool.putconn(self._conn)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, *_):
        try:
            self._conn.rollback()
        except Exception:
            pass
        self._pool.putconn(self._conn)


def get_connection(schema=SCHEMA):
    """Return a pooled Postgres connection with search_path set to schema."""
    pool = _get_pg_pool()
    conn = pool.getconn()
    try:
        conn.autocommit = False
        pg_conn = _PgConn(pool, conn)
        _cur = conn.cursor()
        _cur.execute(f"SET search_path = {schema}, public")
        _cur.close()
        return pg_conn
    except Exception:
        pool.putconn(conn)
        raise


def get_willow_knowledge_connection():
    """Return a Postgres connection with search_path = sweet_pea_rudi19 (Willow knowledge schema)."""
    return get_connection(schema="sweet_pea_rudi19")


def init_schema():
    """Create the nasa_archive schema if it does not exist."""
    pool = _get_pg_pool()
    conn = pool.getconn()
    try:
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
        cur.close()
    finally:
        pool.putconn(conn)


def is_postgres():
    """Always True -- this codebase is PostgreSQL-only."""
    return DATABASE_URL.startswith("postgresql")
