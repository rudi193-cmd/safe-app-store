"""
genealogy_db.py -- Genealogy database module using the 23-cubed lattice structure.

PostgreSQL-only. Schema: genealogy.
Each person maps into a 23x23x23 lattice (12,167 cells per entity).

Lattice constants imported from Willow's user_lattice.py.
DB connection follows Willow's core/db.py pattern (psycopg2, pooled).
"""

import os
import sys
import threading
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple

# Import 23-cubed lattice constants from Willow
sys.path.insert(0, os.environ.get("WILLOW_CORE", "/home/sean-campbell/github/Willow/core"))
from user_lattice import DOMAINS, TEMPORAL_STATES, DEPTH_MIN, DEPTH_MAX, LATTICE_SIZE

# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

_pool = None
_pool_lock = threading.Lock()

SCHEMA = "genealogy"


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
    """Return a pooled Postgres connection with search_path = genealogy, public."""
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

VALID_RELATIONSHIP_TYPES = frozenset({"parent", "child", "spouse", "sibling"})
VALID_SOURCE_TYPES = frozenset({"findagrave", "familysearch", "census", "document", "oral"})


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
    """Create the genealogy schema and all tables. Idempotent."""
    cur = conn.cursor()

    cur.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    cur.execute(f"SET search_path = {SCHEMA}, public")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS persons (
            id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            full_name   TEXT NOT NULL,
            birth_date  TEXT,
            birth_place TEXT,
            death_date  TEXT,
            death_place TEXT,
            burial_place TEXT,
            memorial_id TEXT,
            memorial_url TEXT,
            bio         TEXT,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_deleted  BOOLEAN DEFAULT FALSE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS relationships (
            id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            person_id         BIGINT NOT NULL REFERENCES persons(id),
            related_person_id BIGINT NOT NULL REFERENCES persons(id),
            relationship_type TEXT NOT NULL CHECK (relationship_type IN ('parent','child','spouse','sibling')),
            created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS lattice_cells (
            id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            person_id   BIGINT NOT NULL REFERENCES persons(id),
            domain      TEXT NOT NULL,
            depth       INTEGER NOT NULL CHECK (depth >= 1 AND depth <= 23),
            temporal    TEXT NOT NULL,
            content     TEXT NOT NULL,
            source      TEXT,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_sensitive BOOLEAN DEFAULT FALSE,
            UNIQUE(person_id, domain, depth, temporal)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sources (
            id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            person_id    BIGINT NOT NULL REFERENCES persons(id),
            source_type  TEXT NOT NULL CHECK (source_type IN ('findagrave','familysearch','census','document','oral')),
            source_url   TEXT,
            source_title TEXT,
            raw_content  TEXT,
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Indices
    cur.execute("CREATE INDEX IF NOT EXISTS idx_persons_name ON persons (full_name)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_rel_person ON relationships (person_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_rel_related ON relationships (related_person_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_lc_person ON lattice_cells (person_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_lc_domain ON lattice_cells (domain)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_lc_temporal ON lattice_cells (temporal)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sources_person ON sources (person_id)")

    conn.commit()


# ---------------------------------------------------------------------------
# CRUD -- all return new dicts (immutable pattern)
# ---------------------------------------------------------------------------

def add_person(conn, *, full_name: str, birth_date: str = None, birth_place: str = None,
               death_date: str = None, death_place: str = None, burial_place: str = None,
               memorial_id: str = None, memorial_url: str = None, bio: str = None) -> Dict[str, Any]:
    """Insert a person. Returns a dict with the new row (including id)."""
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO persons (full_name, birth_date, birth_place, death_date, death_place,
                             burial_place, memorial_id, memorial_url, bio)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id, full_name, birth_date, birth_place, death_date, death_place,
                  burial_place, memorial_id, memorial_url, bio, created_at, updated_at, is_deleted
    """, (full_name, birth_date, birth_place, death_date, death_place,
          burial_place, memorial_id, memorial_url, bio))
    row = cur.fetchone()
    cols = [d[0] for d in cur.description]
    conn.commit()
    return dict(zip(cols, row))


def add_relationship(conn, person_id: int, related_id: int, rel_type: str) -> Dict[str, Any]:
    """Link two persons. Returns the new relationship row as a dict."""
    if rel_type not in VALID_RELATIONSHIP_TYPES:
        raise ValueError(f"Invalid relationship_type '{rel_type}'. Must be one of: {VALID_RELATIONSHIP_TYPES}")
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO relationships (person_id, related_person_id, relationship_type)
        VALUES (%s, %s, %s)
        RETURNING id, person_id, related_person_id, relationship_type, created_at
    """, (person_id, related_id, rel_type))
    row = cur.fetchone()
    cols = [d[0] for d in cur.description]
    conn.commit()
    return dict(zip(cols, row))


def add_source(conn, person_id: int, source_type: str, url: str = None,
               title: str = None, content: str = None) -> Dict[str, Any]:
    """Attach a source to a person. Returns the new source row as a dict."""
    if source_type not in VALID_SOURCE_TYPES:
        raise ValueError(f"Invalid source_type '{source_type}'. Must be one of: {VALID_SOURCE_TYPES}")
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO sources (person_id, source_type, source_url, source_title, raw_content)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id, person_id, source_type, source_url, source_title, raw_content, created_at
    """, (person_id, source_type, url, title, content))
    row = cur.fetchone()
    cols = [d[0] for d in cur.description]
    conn.commit()
    return dict(zip(cols, row))


def place_in_lattice(conn, person_id: int, domain: str, depth: int, temporal: str,
                     content: str, source: str = None, is_sensitive: bool = False) -> Dict[str, Any]:
    """Map a person to a lattice cell. Upserts on (person_id, domain, depth, temporal).
    Returns the cell row as a dict."""
    _validate_lattice(domain, depth, temporal)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO lattice_cells (person_id, domain, depth, temporal, content, source, is_sensitive)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (person_id, domain, depth, temporal)
        DO UPDATE SET content = EXCLUDED.content, source = EXCLUDED.source, is_sensitive = EXCLUDED.is_sensitive
        RETURNING id, person_id, domain, depth, temporal, content, source, created_at, is_sensitive
    """, (person_id, domain, depth, temporal, content, source, is_sensitive))
    row = cur.fetchone()
    cols = [d[0] for d in cur.description]
    conn.commit()
    return dict(zip(cols, row))


def get_family_tree(conn, person_id: int) -> Dict[str, Any]:
    """Return the person record plus all relationships (as dicts). Immutable result."""
    cur = conn.cursor()

    cur.execute("SELECT * FROM persons WHERE id = %s AND is_deleted = FALSE", (person_id,))
    person_row = cur.fetchone()
    if person_row is None:
        return {"person": None, "relationships": []}
    pcols = [d[0] for d in cur.description]
    person = dict(zip(pcols, person_row))

    cur.execute("""
        SELECT r.*, p.full_name AS related_name
        FROM relationships r
        JOIN persons p ON p.id = r.related_person_id
        WHERE r.person_id = %s
        UNION ALL
        SELECT r.*, p.full_name AS related_name
        FROM relationships r
        JOIN persons p ON p.id = r.person_id
        WHERE r.related_person_id = %s
    """, (person_id, person_id))
    rows = cur.fetchall()
    rcols = [d[0] for d in cur.description]
    rels = [dict(zip(rcols, r)) for r in rows]

    return {"person": person, "relationships": rels}


def search_persons(conn, name_query: str) -> List[Dict[str, Any]]:
    """Search persons by name (case-insensitive ILIKE). Returns list of dicts."""
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM persons
        WHERE full_name ILIKE %s AND is_deleted = FALSE
        ORDER BY full_name
    """, (f"%{name_query}%",))
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in rows]
