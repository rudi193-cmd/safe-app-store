"""
db — The Squirrel database package.
b17: NNA92
ΔΣ=42

Schema: the_squirrel

PII layer    — db.persons   (persons, relationships, person_lattice_cells, person_sources)
             — db.fragments (fragments, tree_branches, fragment_lattice_cells)
System layer — db.sources   (source_registry — no PII, user-agnostic, no gate required)

PII and system data share the schema but are handled by separate modules.
SAP gate must be checked by callers before any PII read/write.
"""

import os
import sys
import threading

# ---------------------------------------------------------------------------
# Willow lattice constants — required at import time
# ---------------------------------------------------------------------------

_willow_core = os.environ.get("WILLOW_CORE")
if not _willow_core:
    raise EnvironmentError("WILLOW_CORE env var not set. Point it to your Willow/core directory.")
sys.path.insert(0, _willow_core)
from user_lattice import DOMAINS, TEMPORAL_STATES, DEPTH_MIN, DEPTH_MAX, LATTICE_SIZE  # noqa: E402

# ---------------------------------------------------------------------------
# Connection pool
# ---------------------------------------------------------------------------

SCHEMA = "the_squirrel"

_pool = None
_pool_lock = threading.Lock()


def _default_dsn() -> str:
    """Build DSN for Unix socket connection — no host, peer auth via OS user."""
    import pwd
    db = os.environ.get("WILLOW_PG_DB", "willow")
    user = os.environ.get("WILLOW_PG_USER", pwd.getpwuid(os.getuid()).pw_name)
    return f"dbname={db} user={user}"


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


def get_connection():
    """Return a pooled Postgres connection with search_path = the_squirrel, public."""
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


def release_connection(conn):
    """Return a connection to the pool."""
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
