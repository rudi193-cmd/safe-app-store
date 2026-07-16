"""
db — The Squirrel database package.
b17: NNA92
ΔΣ=42

PII layer    — db.persons   (persons, relationships, person_lattice_cells, person_sources)
             — db.fragments (fragments, tree_branches, fragment_lattice_cells)
System layer — db.sources   (source_registry — no PII, user-agnostic, no gate required)

SAP gate must be checked by callers before any PII read/write.

Backends (Phase 1, 2026-07-16 — the flagship bar: zero Willow, zero Postgres):

  sqlite   DEFAULT. The box's own file: $SQUIRREL_HOME/squirrel.db
           (override: SQUIRREL_DB). Auto-migrates on first connection and
           seeds the 779-archive source registry from data/. No env vars,
           no server, no seed rituals.
  postgres The Willow mode, now opt-in: SQUIRREL_BACKEND=postgres or a
           WILLOW_DB_URL. Same module code — the SQL is written once in
           the Postgres dialect; the SQLite connection translates.

Lattice constants come from Willow's user_lattice when WILLOW_CORE is set,
else from the vendored db.lattice_constants. Willow is an upgrade, never
a requirement.
"""

import json as _json
import os
import re
import sys
import threading

# ---------------------------------------------------------------------------
# Lattice constants — Willow if present, vendored otherwise
# ---------------------------------------------------------------------------

_willow_core = os.environ.get("WILLOW_CORE")
if _willow_core:
    sys.path.insert(0, _willow_core)
    try:
        from user_lattice import DOMAINS, TEMPORAL_STATES, DEPTH_MIN, DEPTH_MAX, LATTICE_SIZE  # noqa: F401
    except ImportError:
        from db.lattice_constants import DOMAINS, TEMPORAL_STATES, DEPTH_MIN, DEPTH_MAX, LATTICE_SIZE  # noqa: F401
else:
    from db.lattice_constants import DOMAINS, TEMPORAL_STATES, DEPTH_MIN, DEPTH_MAX, LATTICE_SIZE  # noqa: F401

SCHEMA = "the_squirrel"


def _backend() -> str:
    if os.environ.get("SQUIRREL_BACKEND", "").lower() == "postgres":
        return "postgres"
    if os.environ.get("WILLOW_DB_URL"):
        return "postgres"
    return "sqlite"


BACKEND = _backend()

# ---------------------------------------------------------------------------
# SQLite backend — the default. The module SQL stays in the Postgres dialect;
# this thin cursor translates the handful of constructs that differ. sources.py
# carries the one genuine fork (tsvector FTS has no cheap translation).
# ---------------------------------------------------------------------------

_XLATE = [
    (re.compile(r"BIGINT\s+GENERATED\s+ALWAYS\s+AS\s+IDENTITY\s+PRIMARY\s+KEY", re.I),
     "INTEGER PRIMARY KEY AUTOINCREMENT"),
    (re.compile(r"\bILIKE\b", re.I), "LIKE"),        # SQLite LIKE is already case-insensitive
    (re.compile(r"\bJSONB\b", re.I), "TEXT"),
    (re.compile(r"INTEGER\[\]", re.I), "TEXT"),      # arrays stored as JSON text
    (re.compile(r"TIMESTAMPTZ\s+DEFAULT\s+now\(\)", re.I), "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
    (re.compile(re.escape(SCHEMA + ".")), ""),       # no schemas in SQLite
]
_SKIP = re.compile(r"^\s*(CREATE\s+SCHEMA|SET\s+search_path)", re.I)


def _to_sqlite(sql: str):
    """Translate one statement; None means 'no-op on SQLite'."""
    if _SKIP.match(sql):
        return None
    sql = sql.replace("%s", "?")
    for pattern, replacement in _XLATE:
        sql = pattern.sub(replacement, sql)
    return sql


def _adapt_param(p):
    if isinstance(p, (list, tuple)):
        return _json.dumps(list(p))
    if isinstance(p, dict):
        return _json.dumps(p)
    return p


class _SqliteCursor:
    def __init__(self, cur):
        self._cur = cur

    def execute(self, sql, params=()):
        translated = _to_sqlite(sql)
        if translated is not None:
            self._cur.execute(translated, tuple(_adapt_param(p) for p in params))
        return self

    def __getattr__(self, name):  # description, fetchone, fetchall, rowcount, close…
        return getattr(self._cur, name)


class _SqliteConnection:
    def __init__(self, conn):
        self._conn = conn

    def cursor(self):
        return _SqliteCursor(self._conn.cursor())

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


def _sqlite_path() -> str:
    from sap.core.vault import squirrel_home
    return os.environ.get("SQUIRREL_DB", str(squirrel_home() / "squirrel.db"))


_ready_paths = set()
_ready_lock = threading.Lock()


def _ensure_ready(conn, path: str):
    """First connection to a fresh box: create every table, seed the source
    registry. Idempotent and cheap afterwards (guarded per path per process)."""
    with _ready_lock:
        if path in _ready_paths:
            return
        import db.persons, db.fragments, db.sources, db.events, db.media  # noqa: E401
        db.persons.init_schema(conn)
        db.fragments.init_schema(conn)
        db.sources.init_schema(conn)
        db.events.init_schema(conn)
        db.media.init_schema(conn)
        if not os.environ.get("SQUIRREL_SKIP_SEED"):
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM source_registry")
            if cur.fetchone()[0] == 0 and db.sources.CHA_JSON.exists():
                db.sources.seed_from_json(conn)
        _ready_paths.add(path)


# ---------------------------------------------------------------------------
# Postgres backend — the Willow mode, opt-in
# ---------------------------------------------------------------------------

_pool = None
_pool_lock = threading.Lock()


def _default_dsn() -> str:
    """Unix-socket DSN — no host, peer auth via OS user."""
    import pwd
    db_name = os.environ.get("WILLOW_PG_DB", "willow")
    user = os.environ.get("WILLOW_PG_USER", pwd.getpwuid(os.getuid()).pw_name)
    return f"dbname={db_name} user={user}"


def _get_pool():
    global _pool
    if _pool is not None:
        return _pool
    with _pool_lock:
        if _pool is None:
            import psycopg2.pool
            dsn = os.getenv("WILLOW_DB_URL") or _default_dsn()
            _pool = psycopg2.pool.ThreadedConnectionPool(minconn=1, maxconn=10, dsn=dsn)
    return _pool


# ---------------------------------------------------------------------------
# The seam
# ---------------------------------------------------------------------------

def get_connection():
    if _backend() == "postgres":
        pool = _get_pool()
        conn = pool.getconn()
        try:
            conn.autocommit = False
            cur = conn.cursor()
            cur.execute(f"SET search_path = {SCHEMA}, public")
            cur.close()
            return conn
        except Exception:
            pool.putconn(conn)
            raise
    import sqlite3
    path = _sqlite_path()
    if path != ":memory:":
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    raw = sqlite3.connect(path, check_same_thread=False)
    raw.execute("PRAGMA journal_mode=WAL")
    raw.execute("PRAGMA foreign_keys=ON")
    conn = _SqliteConnection(raw)
    _ensure_ready(conn, path)
    return conn


def release_connection(conn):
    if isinstance(conn, _SqliteConnection):
        try:
            conn.rollback()
        except Exception:
            pass
        conn.close()
        return
    try:
        conn.rollback()
    except Exception:
        pass
    _get_pool().putconn(conn)


# ---------------------------------------------------------------------------
# Shared lattice validation
# ---------------------------------------------------------------------------

def _validate_lattice(domain: str, depth: int, temporal: str):
    if domain not in DOMAINS:
        raise ValueError(f"Invalid domain '{domain}'. Must be one of: {DOMAINS}")
    if not (DEPTH_MIN <= depth <= DEPTH_MAX):
        raise ValueError(f"Invalid depth {depth}. Must be {DEPTH_MIN}-{DEPTH_MAX}")
    if temporal not in TEMPORAL_STATES:
        raise ValueError(f"Invalid temporal '{temporal}'. Must be one of: {TEMPORAL_STATES}")
