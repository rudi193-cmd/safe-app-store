"""
wellbeing_db.py -- Dating wellbeing database using the 23-cubed lattice structure.

PostgreSQL-only. Schema: dating_wellbeing.
Each entity (profile, interaction, pattern) maps into a 23x23x23 lattice.

CRITICAL: ALL data defaults to is_sensitive=1. This is the most privacy-sensitive app.

Lattice constants imported from Willow's user_lattice.py.
DB connection follows Willow's core/db.py pattern (psycopg2, pooled).
"""

import os
import sys
import threading
from datetime import datetime
from typing import Optional, List, Dict, Any

# Import 23-cubed lattice constants from Willow
sys.path.insert(0, os.environ.get("WILLOW_CORE", "/home/sean-campbell/github/Willow/core"))
from user_lattice import DOMAINS, TEMPORAL_STATES, DEPTH_MIN, DEPTH_MAX, LATTICE_SIZE

# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

_pool = None
_pool_lock = threading.Lock()

SCHEMA = "dating_wellbeing"


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
    """Return a pooled Postgres connection with search_path = dating_wellbeing, public."""
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

VALID_PLATFORMS = frozenset({"feeld", "hinge", "tinder", "match", "eharmony", "other"})
VALID_STATUSES = frozenset({"active", "paused", "archived", "unmatched"})
VALID_INTERACTION_TYPES = frozenset({"match", "message", "date", "unmatch", "block", "note"})
VALID_SENTIMENTS = frozenset({"positive", "neutral", "negative", "mixed"})
VALID_PATTERN_TYPES = frozenset({"red_flag", "green_flag", "growth_note", "boundary", "preference"})
VALID_CONFIDENCE = frozenset({"low", "medium", "high"})
VALID_ENTITY_TYPES = frozenset({"profile", "interaction", "pattern"})


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
    """Create the dating_wellbeing schema and all tables. Idempotent."""
    cur = conn.cursor()

    cur.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    cur.execute(f"SET search_path = {SCHEMA}, public")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS profiles (
            id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            platform     TEXT NOT NULL CHECK (platform IN ('feeld','hinge','tinder','match','eharmony','other')),
            display_name TEXT NOT NULL,
            status       TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','paused','archived','unmatched')),
            first_seen   TIMESTAMP,
            last_seen    TIMESTAMP,
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_deleted   BOOLEAN DEFAULT FALSE,
            is_sensitive BOOLEAN DEFAULT TRUE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS interactions (
            id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            profile_id       BIGINT NOT NULL REFERENCES profiles(id),
            interaction_type TEXT NOT NULL CHECK (interaction_type IN ('match','message','date','unmatch','block','note')),
            interaction_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            content_summary  TEXT,
            sentiment        TEXT CHECK (sentiment IN ('positive','neutral','negative','mixed')),
            created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS patterns (
            id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            pattern_type   TEXT NOT NULL CHECK (pattern_type IN ('red_flag','green_flag','growth_note','boundary','preference')),
            description    TEXT NOT NULL,
            confidence     TEXT NOT NULL DEFAULT 'medium' CHECK (confidence IN ('low','medium','high')),
            source_context TEXT,
            created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active      BOOLEAN DEFAULT TRUE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS lattice_cells (
            id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            entity_id    BIGINT NOT NULL,
            entity_type  TEXT NOT NULL CHECK (entity_type IN ('profile','interaction','pattern')),
            domain       TEXT NOT NULL,
            depth        INTEGER NOT NULL CHECK (depth >= 1 AND depth <= 23),
            temporal     TEXT NOT NULL,
            content      TEXT NOT NULL,
            source       TEXT,
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_sensitive BOOLEAN DEFAULT TRUE,
            UNIQUE(entity_id, entity_type, domain, depth, temporal)
        )
    """)

    # Indices
    cur.execute("CREATE INDEX IF NOT EXISTS idx_profiles_platform ON profiles (platform)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_profiles_status ON profiles (status)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_profiles_name ON profiles (display_name)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_interactions_profile ON interactions (profile_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_interactions_type ON interactions (interaction_type)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_interactions_date ON interactions (interaction_date)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_patterns_type ON patterns (pattern_type)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_patterns_active ON patterns (is_active)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_lc_entity ON lattice_cells (entity_id, entity_type)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_lc_domain ON lattice_cells (domain)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_lc_temporal ON lattice_cells (temporal)")

    conn.commit()


# ---------------------------------------------------------------------------
# CRUD -- all return new dicts (immutable pattern)
# ---------------------------------------------------------------------------

def add_profile(conn, *, platform: str, display_name: str, status: str = "active",
                first_seen: str = None, last_seen: str = None) -> Dict[str, Any]:
    """Insert a profile. Returns a dict with the new row (including id)."""
    if platform not in VALID_PLATFORMS:
        raise ValueError(f"Invalid platform '{platform}'. Must be one of: {VALID_PLATFORMS}")
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid status '{status}'. Must be one of: {VALID_STATUSES}")
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO profiles (platform, display_name, status, first_seen, last_seen)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id, platform, display_name, status, first_seen, last_seen,
                  created_at, updated_at, is_deleted, is_sensitive
    """, (platform, display_name, status, first_seen, last_seen))
    row = cur.fetchone()
    cols = [d[0] for d in cur.description]
    conn.commit()
    return dict(zip(cols, row))


def add_interaction(conn, *, profile_id: int, interaction_type: str,
                    interaction_date: str = None, content_summary: str = None,
                    sentiment: str = None) -> Dict[str, Any]:
    """Insert an interaction. Returns a dict with the new row."""
    if interaction_type not in VALID_INTERACTION_TYPES:
        raise ValueError(f"Invalid interaction_type '{interaction_type}'. Must be one of: {VALID_INTERACTION_TYPES}")
    if sentiment is not None and sentiment not in VALID_SENTIMENTS:
        raise ValueError(f"Invalid sentiment '{sentiment}'. Must be one of: {VALID_SENTIMENTS}")
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO interactions (profile_id, interaction_type, interaction_date, content_summary, sentiment)
        VALUES (%s, %s, COALESCE(%s::timestamp, CURRENT_TIMESTAMP), %s, %s)
        RETURNING id, profile_id, interaction_type, interaction_date, content_summary, sentiment, created_at
    """, (profile_id, interaction_type, interaction_date, content_summary, sentiment))
    row = cur.fetchone()
    cols = [d[0] for d in cur.description]
    conn.commit()
    return dict(zip(cols, row))


def add_pattern(conn, *, pattern_type: str, description: str, confidence: str = "medium",
                source_context: str = None) -> Dict[str, Any]:
    """Insert a pattern. Returns a dict with the new row."""
    if pattern_type not in VALID_PATTERN_TYPES:
        raise ValueError(f"Invalid pattern_type '{pattern_type}'. Must be one of: {VALID_PATTERN_TYPES}")
    if confidence not in VALID_CONFIDENCE:
        raise ValueError(f"Invalid confidence '{confidence}'. Must be one of: {VALID_CONFIDENCE}")
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO patterns (pattern_type, description, confidence, source_context)
        VALUES (%s, %s, %s, %s)
        RETURNING id, pattern_type, description, confidence, source_context, created_at, is_active
    """, (pattern_type, description, confidence, source_context))
    row = cur.fetchone()
    cols = [d[0] for d in cur.description]
    conn.commit()
    return dict(zip(cols, row))


def place_in_lattice(conn, *, entity_id: int, entity_type: str, domain: str,
                     depth: int, temporal: str, content: str,
                     source: str = None) -> Dict[str, Any]:
    """Map an entity to a lattice cell. Upserts on (entity_id, entity_type, domain, depth, temporal).
    is_sensitive always defaults to TRUE. Returns the cell row as a dict."""
    if entity_type not in VALID_ENTITY_TYPES:
        raise ValueError(f"Invalid entity_type '{entity_type}'. Must be one of: {VALID_ENTITY_TYPES}")
    _validate_lattice(domain, depth, temporal)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO lattice_cells (entity_id, entity_type, domain, depth, temporal, content, source)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (entity_id, entity_type, domain, depth, temporal)
        DO UPDATE SET content = EXCLUDED.content, source = EXCLUDED.source
        RETURNING id, entity_id, entity_type, domain, depth, temporal, content, source, created_at, is_sensitive
    """, (entity_id, entity_type, domain, depth, temporal, content, source))
    row = cur.fetchone()
    cols = [d[0] for d in cur.description]
    conn.commit()
    return dict(zip(cols, row))


def get_platform_summary(conn, platform: str = None) -> List[Dict[str, Any]]:
    """Return summary counts per platform. Optionally filter to one platform."""
    cur = conn.cursor()
    if platform:
        if platform not in VALID_PLATFORMS:
            raise ValueError(f"Invalid platform '{platform}'. Must be one of: {VALID_PLATFORMS}")
        cur.execute("""
            SELECT p.platform,
                   COUNT(DISTINCT p.id) AS profile_count,
                   COUNT(DISTINCT i.id) AS interaction_count,
                   MIN(p.first_seen) AS earliest_seen,
                   MAX(p.last_seen) AS latest_seen
            FROM profiles p
            LEFT JOIN interactions i ON i.profile_id = p.id
            WHERE p.is_deleted = FALSE AND p.platform = %s
            GROUP BY p.platform
        """, (platform,))
    else:
        cur.execute("""
            SELECT p.platform,
                   COUNT(DISTINCT p.id) AS profile_count,
                   COUNT(DISTINCT i.id) AS interaction_count,
                   MIN(p.first_seen) AS earliest_seen,
                   MAX(p.last_seen) AS latest_seen
            FROM profiles p
            LEFT JOIN interactions i ON i.profile_id = p.id
            WHERE p.is_deleted = FALSE
            GROUP BY p.platform
            ORDER BY p.platform
        """)
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in rows]


def search_patterns(conn, query: str = None, pattern_type: str = None,
                    active_only: bool = True) -> List[Dict[str, Any]]:
    """Search patterns by text query and/or type. Returns list of dicts."""
    conditions = []
    params = []
    if active_only:
        conditions.append("is_active = TRUE")
    if pattern_type:
        if pattern_type not in VALID_PATTERN_TYPES:
            raise ValueError(f"Invalid pattern_type '{pattern_type}'. Must be one of: {VALID_PATTERN_TYPES}")
        conditions.append("pattern_type = %s")
        params.append(pattern_type)
    if query:
        conditions.append("(description ILIKE %s OR source_context ILIKE %s)")
        params.extend([f"%{query}%", f"%{query}%"])

    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    cur = conn.cursor()
    cur.execute(f"""
        SELECT * FROM patterns
        {where}
        ORDER BY created_at DESC
    """, params)
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in rows]
