"""
db.py -- Database connection abstraction for Law Gazelle.

PostgreSQL-only. All data lives in the ``law_gazelle`` schema.
Requires WILLOW_DB_URL=postgresql://... in the environment.
All code calls get_connection() -- never sqlite3.connect() directly.
"""
import os
import threading

DATABASE_URL = os.getenv("WILLOW_DB_URL", "")
if not DATABASE_URL:
    raise RuntimeError("WILLOW_DB_URL is not set. Set it to postgresql://user:pass@host:port/db")

SCHEMA_NAME = "law_gazelle"

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
                raise RuntimeError("psycopg2 not installed. Run: pip install psycopg2-binary")
    return _pg_pool


import re as _re

# The SQLite->Postgres compatibility shim now lives in libs/pg-sqlite-shim
# (box audit A5): sqlite_to_pg() + the PgCursor/PgConn sqlite3-compat wrappers.
# The shared shim is nasa-archive's hardened form — a SAVEPOINT-guarded
# lastval() and a RETURNING-aware lastrowid — which supersedes the simpler
# lastrowid this app used to carry (an accepted improvement). psycopg2 stays a
# lazy import inside the shim, so importing this module needs no driver.
from pg_sqlite_shim import PgConn as _PgConn

# Conflict targets for INSERT OR REPLACE upserts (extend as needed).
# App-specific data: kept here and passed into the shim per connection.
_PG_CONFLICT_TARGETS: dict = {}


def get_connection(path: str = None, schema: str = SCHEMA_NAME):
    """Return a pooled Postgres connection scoped to law_gazelle schema.
    path is ignored (kept for call-site compatibility during migration)."""
    # Schema names can't be parameterized — validate before the f-string
    # interpolation below (ST-SQL-01).
    if schema and not _re.fullmatch(r"[a-z_][a-z0-9_]*", schema):
        raise ValueError(f"Invalid schema name: {schema!r}")
    pool = _get_pg_pool()
    conn = pool.getconn()
    try:
        conn.autocommit = False
        # commit_on_exit=True preserves this app's context-manager contract:
        # `with get_connection() as conn:` commits on a clean exit.
        pg_conn = _PgConn(pool, conn, conflict_targets=_PG_CONFLICT_TARGETS,
                          commit_on_exit=True)
        if schema:
            from psycopg2 import sql as _sql
            cur = conn.cursor()
            cur.execute(_sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(_sql.Identifier(schema)))
            cur.execute(_sql.SQL("SET search_path = {}, public").format(_sql.Identifier(schema)))
            cur.close()
            conn.commit()
        return pg_conn
    except Exception:
        pool.putconn(conn)
        raise


def is_postgres() -> bool:
    return DATABASE_URL.startswith("postgresql")
