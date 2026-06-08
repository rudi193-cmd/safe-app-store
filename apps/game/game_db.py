"""
game_db.py -- TTRPG campaign/game state database using the 23-cubed lattice structure.

PostgreSQL-only. Schema: game_master.
Each entity (campaign, character, session) maps into a 23x23x23 lattice (12,167 cells per entity).

Lattice constants imported from Willow's user_lattice.py.
DB connection follows Willow's core/db.py pattern (psycopg2, pooled).
"""

import json
import os
import sys
import threading
from datetime import datetime
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

SCHEMA = "game_master"

VALID_GAME_SYSTEMS = frozenset({"dnd5e", "pathfinder", "fate", "custom", "other"})
VALID_CAMPAIGN_STATUSES = frozenset({"active", "paused", "completed", "archived"})
VALID_ENTITY_TYPES = frozenset({"campaign", "character", "session"})


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
            dsn = os.getenv("GAME_MASTER_DB_URL") or os.getenv("WILLOW_DB_URL", "")
            if not dsn:
                host = _resolve_host()
                dsn = f"dbname=willow user=game_master_app host={host}"
            _pool = psycopg2.pool.ThreadedConnectionPool(minconn=1, maxconn=10, dsn=dsn)
    return _pool


def get_connection():
    """Return a pooled Postgres connection with search_path = game_master, public."""
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
        raise ValueError(f"Invalid domain \'{domain}\'. Must be one of: {DOMAINS}")
    if not (DEPTH_MIN <= depth <= DEPTH_MAX):
        raise ValueError(f"Invalid depth {depth}. Must be {DEPTH_MIN}-{DEPTH_MAX}")
    if temporal not in TEMPORAL_STATES:
        raise ValueError(f"Invalid temporal \'{temporal}\'. Must be one of: {TEMPORAL_STATES}")


def _validate_game_system(game_system: str):
    if game_system not in VALID_GAME_SYSTEMS:
        raise ValueError(f"Invalid game_system \'{game_system}\'. Must be one of: {VALID_GAME_SYSTEMS}")


def _validate_campaign_status(status: str):
    if status not in VALID_CAMPAIGN_STATUSES:
        raise ValueError(f"Invalid status \'{status}\'. Must be one of: {VALID_CAMPAIGN_STATUSES}")


def _validate_entity_type(entity_type: str):
    if entity_type not in VALID_ENTITY_TYPES:
        raise ValueError(f"Invalid entity_type \'{entity_type}\'. Must be one of: {VALID_ENTITY_TYPES}")


# ---------------------------------------------------------------------------
# Schema init
# ---------------------------------------------------------------------------

def init_schema(conn):
    """Create the game_master schema and all tables. Idempotent."""
    cur = conn.cursor()

    cur.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    cur.execute(f"SET search_path = {SCHEMA}, public")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS campaigns (
            id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            name        TEXT NOT NULL,
            game_system TEXT NOT NULL CHECK (game_system IN ('dnd5e','pathfinder','fate','custom','other')),
            description TEXT,
            status      TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','paused','completed','archived')),
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_deleted  INTEGER DEFAULT 0
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS characters (
            id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            campaign_id     BIGINT NOT NULL REFERENCES campaigns(id),
            name            TEXT NOT NULL,
            character_class TEXT,
            level           INTEGER DEFAULT 1,
            stats_json      JSONB,
            backstory       TEXT,
            player_name     TEXT,
            is_npc          BOOLEAN DEFAULT FALSE,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            campaign_id      BIGINT NOT NULL REFERENCES campaigns(id),
            session_number   INTEGER NOT NULL,
            session_date     TEXT,
            summary          TEXT,
            scene_state_json JSONB,
            duration_minutes INTEGER,
            created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS lattice_cells (
            id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            entity_id    BIGINT NOT NULL,
            entity_type  TEXT NOT NULL CHECK (entity_type IN ('campaign','character','session')),
            domain       TEXT NOT NULL,
            depth        INTEGER NOT NULL CHECK (depth >= 1 AND depth <= 23),
            temporal     TEXT NOT NULL,
            content      TEXT NOT NULL,
            source       TEXT,
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_sensitive INTEGER DEFAULT 0,
            UNIQUE(entity_id, entity_type, domain, depth, temporal)
        )
    """)

    # Indices
    cur.execute("CREATE INDEX IF NOT EXISTS idx_campaigns_name ON campaigns (name)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_campaigns_status ON campaigns (status)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_characters_campaign ON characters (campaign_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_characters_name ON characters (name)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_campaign ON sessions (campaign_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_number ON sessions (campaign_id, session_number)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_lc_entity ON lattice_cells (entity_id, entity_type)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_lc_domain ON lattice_cells (domain)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_lc_temporal ON lattice_cells (temporal)")

    conn.commit()


# ---------------------------------------------------------------------------
# CRUD -- all return new dicts (immutable pattern)
# ---------------------------------------------------------------------------

def add_campaign(conn, *, name: str, game_system: str, description: str = None,
                 status: str = "active") -> Dict[str, Any]:
    """Insert a campaign. Returns a dict with the new row (including id)."""
    _validate_game_system(game_system)
    _validate_campaign_status(status)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO campaigns (name, game_system, description, status)
        VALUES (%s, %s, %s, %s)
        RETURNING id, name, game_system, description, status, created_at, updated_at, is_deleted
    """, (name, game_system, description, status))
    row = cur.fetchone()
    cols = [d[0] for d in cur.description]
    conn.commit()
    return dict(zip(cols, row))


def add_character(conn, *, campaign_id: int, name: str, character_class: str = None,
                  level: int = 1, stats_json: Dict = None, backstory: str = None,
                  player_name: str = None, is_npc: bool = False) -> Dict[str, Any]:
    """Insert a character into a campaign. Returns the new row as a dict."""
    if level < 1:
        raise ValueError(f"Level must be >= 1, got {level}")
    stats_value = json.dumps(stats_json) if stats_json is not None else None
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO characters (campaign_id, name, character_class, level, stats_json,
                                backstory, player_name, is_npc)
        VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s)
        RETURNING id, campaign_id, name, character_class, level, stats_json,
                  backstory, player_name, is_npc, created_at, updated_at
    """, (campaign_id, name, character_class, level, stats_value,
          backstory, player_name, is_npc))
    row = cur.fetchone()
    cols = [d[0] for d in cur.description]
    conn.commit()
    return dict(zip(cols, row))


def add_session(conn, *, campaign_id: int, session_number: int, session_date: str = None,
                summary: str = None, scene_state_json: Dict = None,
                duration_minutes: int = None) -> Dict[str, Any]:
    """Record a game session. Returns the new row as a dict."""
    if session_number < 1:
        raise ValueError(f"session_number must be >= 1, got {session_number}")
    scene_value = json.dumps(scene_state_json) if scene_state_json is not None else None
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO sessions (campaign_id, session_number, session_date, summary,
                              scene_state_json, duration_minutes)
        VALUES (%s, %s, %s, %s, %s::jsonb, %s)
        RETURNING id, campaign_id, session_number, session_date, summary,
                  scene_state_json, duration_minutes, created_at
    """, (campaign_id, session_number, session_date, summary,
          scene_value, duration_minutes))
    row = cur.fetchone()
    cols = [d[0] for d in cur.description]
    conn.commit()
    return dict(zip(cols, row))


def place_in_lattice(conn, entity_id: int, entity_type: str, domain: str, depth: int,
                     temporal: str, content: str, source: str = None,
                     is_sensitive: int = 0) -> Dict[str, Any]:
    """Map an entity to a lattice cell. Upserts on (entity_id, entity_type, domain, depth, temporal).
    Returns the cell row as a dict."""
    _validate_entity_type(entity_type)
    _validate_lattice(domain, depth, temporal)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO lattice_cells (entity_id, entity_type, domain, depth, temporal, content, source, is_sensitive)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (entity_id, entity_type, domain, depth, temporal)
        DO UPDATE SET content = EXCLUDED.content, source = EXCLUDED.source, is_sensitive = EXCLUDED.is_sensitive
        RETURNING id, entity_id, entity_type, domain, depth, temporal, content, source, created_at, is_sensitive
    """, (entity_id, entity_type, domain, depth, temporal, content, source, is_sensitive))
    row = cur.fetchone()
    cols = [d[0] for d in cur.description]
    conn.commit()
    return dict(zip(cols, row))


def get_campaign_full(conn, campaign_id: int) -> Dict[str, Any]:
    """Return a campaign with all characters, sessions, and lattice cells. Immutable result."""
    cur = conn.cursor()

    # Campaign
    cur.execute("SELECT * FROM campaigns WHERE id = %s AND is_deleted = 0", (campaign_id,))
    campaign_row = cur.fetchone()
    if campaign_row is None:
        return {"campaign": None, "characters": [], "sessions": [], "lattice_cells": []}
    ccols = [d[0] for d in cur.description]
    campaign = dict(zip(ccols, campaign_row))

    # Characters
    cur.execute("SELECT * FROM characters WHERE campaign_id = %s ORDER BY name", (campaign_id,))
    char_rows = cur.fetchall()
    char_cols = [d[0] for d in cur.description]
    characters = [dict(zip(char_cols, r)) for r in char_rows]

    # Sessions
    cur.execute("SELECT * FROM sessions WHERE campaign_id = %s ORDER BY session_number", (campaign_id,))
    sess_rows = cur.fetchall()
    sess_cols = [d[0] for d in cur.description]
    sessions = [dict(zip(sess_cols, r)) for r in sess_rows]

    # Lattice cells for the campaign itself
    cur.execute("""
        SELECT * FROM lattice_cells
        WHERE entity_id = %s AND entity_type = 'campaign'
        ORDER BY domain, depth, temporal
    """, (campaign_id,))
    lc_rows = cur.fetchall()
    lc_cols = [d[0] for d in cur.description]
    lattice_cells = [dict(zip(lc_cols, r)) for r in lc_rows]

    return {
        "campaign": campaign,
        "characters": characters,
        "sessions": sessions,
        "lattice_cells": lattice_cells,
    }


def search_characters(conn, name_query: str, campaign_id: int = None) -> List[Dict[str, Any]]:
    """Search characters by name (case-insensitive ILIKE). Optionally filter by campaign.
    Returns list of dicts."""
    cur = conn.cursor()
    if campaign_id is not None:
        cur.execute("""
            SELECT c.*, camp.name AS campaign_name
            FROM characters c
            JOIN campaigns camp ON camp.id = c.campaign_id
            WHERE c.name ILIKE %s AND c.campaign_id = %s AND camp.is_deleted = 0
            ORDER BY c.name
        """, (f"%{name_query}%", campaign_id))
    else:
        cur.execute("""
            SELECT c.*, camp.name AS campaign_name
            FROM characters c
            JOIN campaigns camp ON camp.id = c.campaign_id
            WHERE c.name ILIKE %s AND camp.is_deleted = 0
            ORDER BY c.name
        """, (f"%{name_query}%",))
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in rows]
