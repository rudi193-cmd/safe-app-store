"""
squirrel_db.py — DEPRECATED. Use the db/ package instead.

Superseded by db/__init__.py, db/persons.py, db/fragments.py, db/sources.py
as of Level 2 rebuild (2026-04-15).

Differences vs db/ package:
  - Table name: lattice_cells (here) vs fragment_lattice_cells (db/)
  - No SAP gate
  - No persons/relationships/person_sources tables

Kept for reference. Do not use in new code.
"""

import os
import sys
import threading
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple

# Import 23-cubed lattice constants from Willow
_willow_core = os.environ.get("WILLOW_CORE")
if not _willow_core:
    raise EnvironmentError("WILLOW_CORE env var not set")
sys.path.insert(0, _willow_core)
from user_lattice import DOMAINS, TEMPORAL_STATES, DEPTH_MIN, DEPTH_MAX, LATTICE_SIZE

# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

_pool = None
_pool_lock = threading.Lock()

SCHEMA = "the_squirrel"

VALID_FRAGMENT_TYPES = frozenset({"name", "date", "story", "photo", "document", "oral_history"})
VALID_CONFIDENCE_LEVELS = frozenset({"confirmed", "likely", "uncertain", "speculative"})


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
# Validation
# ---------------------------------------------------------------------------

def _validate_lattice(domain: str, depth: int, temporal: str):
    if domain not in DOMAINS:
        raise ValueError(f"Invalid domain '{domain}'. Must be one of: {DOMAINS}")
    if not (DEPTH_MIN <= depth <= DEPTH_MAX):
        raise ValueError(f"Invalid depth {depth}. Must be {DEPTH_MIN}-{DEPTH_MAX}")
    if temporal not in TEMPORAL_STATES:
        raise ValueError(f"Invalid temporal '{temporal}'. Must be one of: {TEMPORAL_STATES}")


# ---------------------------------------------------------------------------
# Schema init
# ---------------------------------------------------------------------------

def init_schema(conn):
    """Create the the_squirrel schema and all tables. Idempotent."""
    cur = conn.cursor()

    cur.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    cur.execute(f"SET search_path = {SCHEMA}, public")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS fragments (
            id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            person_name     TEXT NOT NULL,
            date_ref        TEXT,
            story_text      TEXT,
            photo_ref       TEXT,
            source          TEXT,
            fragment_type   TEXT NOT NULL CHECK (fragment_type IN ('name','date','story','photo','document','oral_history')),
            confidence      TEXT NOT NULL DEFAULT 'uncertain' CHECK (confidence IN ('confirmed','likely','uncertain','speculative')),
            binder_synced_at TIMESTAMP,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_deleted      INTEGER DEFAULT 0
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS tree_branches (
            id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            root_ancestor   TEXT NOT NULL,
            generation_depth INTEGER NOT NULL,
            confirmed_count INTEGER DEFAULT 0,
            fragment_ids    INTEGER[],
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS lattice_cells (
            id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            fragment_id     BIGINT NOT NULL REFERENCES fragments(id),
            domain          TEXT NOT NULL,
            depth           INTEGER NOT NULL CHECK (depth >= 1 AND depth <= 23),
            temporal        TEXT NOT NULL,
            content         TEXT NOT NULL,
            source          TEXT,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_sensitive    BOOLEAN DEFAULT FALSE,
            UNIQUE(fragment_id, domain, depth, temporal)
        )
    """)

    # Indices
    cur.execute("CREATE INDEX IF NOT EXISTS idx_fragments_person ON fragments (person_name)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_fragments_type ON fragments (fragment_type)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_fragments_confidence ON fragments (confidence)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_branches_ancestor ON tree_branches (root_ancestor)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_lc_fragment ON lattice_cells (fragment_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_lc_domain ON lattice_cells (domain)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_lc_temporal ON lattice_cells (temporal)")

    conn.commit()


# ---------------------------------------------------------------------------
# CRUD -- all return new dicts (immutable pattern)
# ---------------------------------------------------------------------------

def add_fragment(conn, *, person_name: str, fragment_type: str, confidence: str = "uncertain",
                 date_ref: str = None, story_text: str = None, photo_ref: str = None,
                 source: str = None) -> Dict[str, Any]:
    """Insert a family fragment. Returns a dict with the new row (including id)."""
    if fragment_type not in VALID_FRAGMENT_TYPES:
        raise ValueError(f"Invalid fragment_type '{fragment_type}'. Must be one of: {VALID_FRAGMENT_TYPES}")
    if confidence not in VALID_CONFIDENCE_LEVELS:
        raise ValueError(f"Invalid confidence '{confidence}'. Must be one of: {VALID_CONFIDENCE_LEVELS}")
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO fragments (person_name, date_ref, story_text, photo_ref, source,
                               fragment_type, confidence)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id, person_name, date_ref, story_text, photo_ref, source,
                  fragment_type, confidence, binder_synced_at, created_at, updated_at, is_deleted
    """, (person_name, date_ref, story_text, photo_ref, source, fragment_type, confidence))
    row = cur.fetchone()
    cols = [d[0] for d in cur.description]
    conn.commit()
    return dict(zip(cols, row))


def add_branch(conn, *, root_ancestor: str, generation_depth: int,
               confirmed_count: int = 0, fragment_ids: List[int] = None) -> Dict[str, Any]:
    """Insert a tree branch. Returns the new row as a dict."""
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO tree_branches (root_ancestor, generation_depth, confirmed_count, fragment_ids)
        VALUES (%s, %s, %s, %s)
        RETURNING id, root_ancestor, generation_depth, confirmed_count, fragment_ids,
                  created_at, updated_at
    """, (root_ancestor, generation_depth, confirmed_count, fragment_ids or []))
    row = cur.fetchone()
    cols = [d[0] for d in cur.description]
    conn.commit()
    return dict(zip(cols, row))


def place_in_lattice(conn, fragment_id: int, domain: str, depth: int, temporal: str,
                     content: str, source: str = None,
                     is_sensitive: bool = False) -> Dict[str, Any]:
    """Map a fragment to a lattice cell. Upserts on (fragment_id, domain, depth, temporal).
    Returns the cell row as a dict."""
    _validate_lattice(domain, depth, temporal)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO lattice_cells (fragment_id, domain, depth, temporal, content, source, is_sensitive)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (fragment_id, domain, depth, temporal)
        DO UPDATE SET content = EXCLUDED.content, source = EXCLUDED.source, is_sensitive = EXCLUDED.is_sensitive
        RETURNING id, fragment_id, domain, depth, temporal, content, source, created_at, is_sensitive
    """, (fragment_id, domain, depth, temporal, content, source, is_sensitive))
    row = cur.fetchone()
    cols = [d[0] for d in cur.description]
    conn.commit()
    return dict(zip(cols, row))


def search_fragments(conn, query: str, fragment_type: str = None) -> List[Dict[str, Any]]:
    """Search fragments by person_name or story_text (case-insensitive ILIKE).
    Optionally filter by fragment_type. Returns list of dicts."""
    cur = conn.cursor()
    if fragment_type is not None:
        if fragment_type not in VALID_FRAGMENT_TYPES:
            raise ValueError(f"Invalid fragment_type '{fragment_type}'. Must be one of: {VALID_FRAGMENT_TYPES}")
        cur.execute("""
            SELECT * FROM fragments
            WHERE (person_name ILIKE %s OR story_text ILIKE %s)
              AND fragment_type = %s AND is_deleted = 0
            ORDER BY created_at DESC
        """, (f"%{query}%", f"%{query}%", fragment_type))
    else:
        cur.execute("""
            SELECT * FROM fragments
            WHERE (person_name ILIKE %s OR story_text ILIKE %s)
              AND is_deleted = 0
            ORDER BY created_at DESC
        """, (f"%{query}%", f"%{query}%"))
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in rows]


def get_unsynced_fragments(conn, limit: int = 100) -> List[Dict[str, Any]]:
    """Return fragments not yet synced to the binder. Immutable result."""
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM fragments
        WHERE binder_synced_at IS NULL AND is_deleted = 0
        ORDER BY created_at ASC
        LIMIT %s
    """, (limit,))
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in rows]


def get_branch_tree(conn, root_ancestor: str) -> List[Dict[str, Any]]:
    """Return all branches for a given root ancestor, with their linked fragments.
    Immutable result."""
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM tree_branches
        WHERE root_ancestor ILIKE %s
        ORDER BY generation_depth ASC
    """, (f"%{root_ancestor}%",))
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in rows]
