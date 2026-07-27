"""
db.py -- Database connection abstraction for nasa-archive.

PostgreSQL-only. All data lives in Postgres under schema nasa_archive.
Requires WILLOW_DB_URL=postgresql://... in the environment.
All code calls get_connection() -- never sqlite3.connect() directly.

Mirrors Willow's core/db.py pattern.
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

# The SQLite->Postgres compatibility shim now lives in libs/pg-sqlite-shim
# (box audit A5): sqlite_to_pg() + the PgCursor/PgConn sqlite3-compat wrappers,
# converged onto this app's hardened form (SAVEPOINT-guarded lastval(),
# RETURNING-aware lastrowid, RealDictCursor row-factory). psycopg2 stays a lazy
# import inside the shim, so importing this module needs no driver.
from pg_sqlite_shim import PgConn as _PgConn

# Conflict targets for INSERT OR REPLACE upserts (table -> ON CONFLICT clause).
# App-specific data: kept here and passed into the shim per connection.
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


# Schema names can't be parameterized, so validate before interpolating (ST-SQL-01).
_SCHEMA_IDENT_RE = _re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def _validate_schema(schema):
    if not _SCHEMA_IDENT_RE.match(schema or ""):
        raise ValueError(f"Invalid schema name: {schema!r}")
    return schema


def get_connection(schema=SCHEMA):
    """Return a pooled Postgres connection with search_path set to schema."""
    _validate_schema(schema)
    from psycopg2 import sql as _sql
    pool = _get_pg_pool()
    conn = pool.getconn()
    try:
        conn.autocommit = False
        pg_conn = _PgConn(pool, conn, conflict_targets=_PG_CONFLICT_TARGETS)
        _cur = conn.cursor()
        _cur.execute(_sql.SQL("SET search_path = {}, public").format(_sql.Identifier(schema)))
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
        _validate_schema(SCHEMA)
        from psycopg2 import sql as _sql
        cur.execute(_sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(_sql.Identifier(SCHEMA)))
        cur.close()
    finally:
        pool.putconn(conn)


def is_postgres() -> bool:
    """Always True -- this codebase is PostgreSQL-only."""
    return DATABASE_URL.startswith("postgresql")
