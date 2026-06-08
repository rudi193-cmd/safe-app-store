"""
notes_db.py -- Personal field notes database using the 23-cubed lattice structure.

PostgreSQL-only. Schema: field_notes.
Each note maps into a 23x23x23 lattice (12,167 cells per entity).

Lattice constants imported from Willow's user_lattice.py.
DB connection follows Willow's core/db.py pattern (psycopg2, pooled).
"""

import os
import sys
import threading
from datetime import datetime, date
from typing import Optional, List, Dict, Any

# Import 23-cubed lattice constants from Willow
sys.path.insert(0, os.environ.get("WILLOW_CORE", os.path.expanduser("~/github/Willow/core")))
try:
    from user_lattice import DOMAINS, TEMPORAL_STATES, DEPTH_MIN, DEPTH_MAX, LATTICE_SIZE
except ImportError:
    # Standalone mode: no Willow checkout. Fall back to app-local constants.
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from lattice_fallback import DOMAINS, TEMPORAL_STATES, DEPTH_MIN, DEPTH_MAX, LATTICE_SIZE

# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

_pool = None
_pool_lock = threading.Lock()

SCHEMA = "field_notes"

VALID_NOTE_TYPES = frozenset({
    "observation", "thought", "quote", "task", "weather", "location",
})


def _resolve_host() -> str:
    """Return localhost, falling back to WSL resolv.conf nameserver."""
    host = "localhost"
    try:
        with open("/etc/resolv.conf") as f:
            for line in f:
                if line.strip().startswith("nameserver"):
                    host = line.strip().split()[1]
                    break
    except FileNotFoundError:
        pass
    return host


def _get_pool():
    global _pool
    if _pool is not None:
        return _pool
    with _pool_lock:
        if _pool is None:
            import psycopg2.pool
            dsn = os.getenv("WILLOW_DB_URL", "")
            if not dsn:
                host = _resolve_host()
                dsn = f"dbname=willow user=willow host={host}"
            _pool = psycopg2.pool.ThreadedConnectionPool(minconn=1, maxconn=10, dsn=dsn)
    return _pool


def get_connection():
    """Return a pooled Postgres connection with search_path = field_notes, public."""
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

def _validate_note_type(note_type: str):
    if note_type not in VALID_NOTE_TYPES:
        raise ValueError(f"Invalid note_type '{note_type}'. Must be one of: {VALID_NOTE_TYPES}")


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
    """Create the field_notes schema and all tables. Idempotent."""
    cur = conn.cursor()

    cur.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    cur.execute(f"SET search_path = {SCHEMA}, public")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            content             TEXT NOT NULL,
            note_type           TEXT NOT NULL CHECK (note_type IN (
                                    'observation','thought','quote','task','weather','location'
                                )),
            tags                TEXT[],
            location_name       TEXT,
            latitude            NUMERIC,
            longitude           NUMERIC,
            weather_summary     TEXT,
            created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            binder_ingested_at  TIMESTAMP,
            is_deleted          BOOLEAN DEFAULT FALSE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS note_tags (
            id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            note_id     BIGINT NOT NULL REFERENCES notes(id),
            tag         TEXT NOT NULL,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(note_id, tag)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS lattice_cells (
            id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            note_id      BIGINT NOT NULL REFERENCES notes(id),
            domain       TEXT NOT NULL,
            depth        INTEGER NOT NULL CHECK (depth >= 1 AND depth <= 23),
            temporal     TEXT NOT NULL,
            content      TEXT NOT NULL,
            source       TEXT,
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_sensitive BOOLEAN DEFAULT FALSE,
            UNIQUE(note_id, domain, depth, temporal)
        )
    """)

    # Indices
    cur.execute("CREATE INDEX IF NOT EXISTS idx_notes_type ON notes (note_type)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_notes_created ON notes (created_at)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_notes_binder ON notes (binder_ingested_at)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_notes_deleted ON notes (is_deleted)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_note_tags_note ON note_tags (note_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_note_tags_tag ON note_tags (tag)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_lc_note ON lattice_cells (note_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_lc_domain ON lattice_cells (domain)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_lc_temporal ON lattice_cells (temporal)")

    conn.commit()


# ---------------------------------------------------------------------------
# CRUD -- all return new dicts (immutable pattern)
# ---------------------------------------------------------------------------

def add_note(conn, *, content: str, note_type: str, tags: List[str] = None,
             location_name: str = None, latitude: float = None, longitude: float = None,
             weather_summary: str = None) -> Dict[str, Any]:
    """Insert a note. Returns a dict with the new row (including id)."""
    _validate_note_type(note_type)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO notes (content, note_type, tags, location_name, latitude, longitude, weather_summary)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id, content, note_type, tags, location_name, latitude, longitude,
                  weather_summary, created_at, updated_at, binder_ingested_at, is_deleted
    """, (content, note_type, tags, location_name, latitude, longitude, weather_summary))
    row = cur.fetchone()
    cols = [d[0] for d in cur.description]
    conn.commit()
    return dict(zip(cols, row))


def add_tags(conn, note_id: int, tags: List[str]) -> List[Dict[str, Any]]:
    """Add tags to a note. Skips duplicates. Returns list of new tag rows."""
    if not tags:
        return []
    cur = conn.cursor()
    results = []
    for tag in tags:
        tag = tag.strip()
        if not tag:
            continue
        cur.execute("""
            INSERT INTO note_tags (note_id, tag)
            VALUES (%s, %s)
            ON CONFLICT (note_id, tag) DO NOTHING
            RETURNING id, note_id, tag, created_at
        """, (note_id, tag))
        row = cur.fetchone()
        if row is not None:
            cols = [d[0] for d in cur.description]
            results.append(dict(zip(cols, row)))
    conn.commit()
    return results


def place_in_lattice(conn, note_id: int, domain: str, depth: int, temporal: str,
                     content: str, source: str = None, is_sensitive: bool = False) -> Dict[str, Any]:
    """Map a note to a lattice cell. Upserts on (note_id, domain, depth, temporal).
    Returns the cell row as a dict."""
    _validate_lattice(domain, depth, temporal)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO lattice_cells (note_id, domain, depth, temporal, content, source, is_sensitive)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (note_id, domain, depth, temporal)
        DO UPDATE SET content = EXCLUDED.content, source = EXCLUDED.source, is_sensitive = EXCLUDED.is_sensitive
        RETURNING id, note_id, domain, depth, temporal, content, source, created_at, is_sensitive
    """, (note_id, domain, depth, temporal, content, source, is_sensitive))
    row = cur.fetchone()
    cols = [d[0] for d in cur.description]
    conn.commit()
    return dict(zip(cols, row))


# ---------------------------------------------------------------------------
# Queries -- immutable returns
# ---------------------------------------------------------------------------

def get_notes_by_date_range(conn, start: date, end: date,
                            note_type: str = None) -> List[Dict[str, Any]]:
    """Return notes within a date range (inclusive). Optionally filter by note_type."""
    cur = conn.cursor()
    if note_type is not None:
        _validate_note_type(note_type)
        cur.execute("""
            SELECT * FROM notes
            WHERE created_at >= %s AND created_at < %s + INTERVAL '1 day'
              AND note_type = %s AND is_deleted = FALSE
            ORDER BY created_at DESC
        """, (start, end, note_type))
    else:
        cur.execute("""
            SELECT * FROM notes
            WHERE created_at >= %s AND created_at < %s + INTERVAL '1 day'
              AND is_deleted = FALSE
            ORDER BY created_at DESC
        """, (start, end))
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in rows]


def search_notes(conn, query: str, note_type: str = None,
                 limit: int = 50) -> List[Dict[str, Any]]:
    """Search notes by content (case-insensitive ILIKE). Returns list of dicts."""
    cur = conn.cursor()
    if note_type is not None:
        _validate_note_type(note_type)
        cur.execute("""
            SELECT * FROM notes
            WHERE content ILIKE %s AND note_type = %s AND is_deleted = FALSE
            ORDER BY created_at DESC
            LIMIT %s
        """, (f"%{query}%", note_type, limit))
    else:
        cur.execute("""
            SELECT * FROM notes
            WHERE content ILIKE %s AND is_deleted = FALSE
            ORDER BY created_at DESC
            LIMIT %s
        """, (f"%{query}%", limit))
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in rows]


def get_unsynced_notes(conn, limit: int = 100) -> List[Dict[str, Any]]:
    """Return notes not yet ingested by the binder (binder_ingested_at IS NULL)."""
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM notes
        WHERE binder_ingested_at IS NULL AND is_deleted = FALSE
        ORDER BY created_at ASC
        LIMIT %s
    """, (limit,))
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in rows]
