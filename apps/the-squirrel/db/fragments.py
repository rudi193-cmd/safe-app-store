"""
db.fragments — PII layer: fragments, tree_branches, fragment_lattice_cells.
Schema: the_squirrel

Fragments are raw genealogical observations — names, dates, stories, photos, documents.
They are the squirrel's stash: collected, unverified, waiting for the Binder.
binder_synced_at tracks when a fragment has been promoted to a person record.

SAP gate (L3-R15): all write functions call sap.core.gate.authorized() before touching PII.
Reads (search_fragments, get_unsynced_fragments, get_branch_tree) are gated on "read".
init_schema() is DDL — no PII, no gate.
"""

from typing import Dict, Any, List
from db import _validate_lattice, SCHEMA
import sap.core.gate as _gate

VALID_FRAGMENT_TYPES = frozenset({"name", "date", "story", "photo", "document", "oral_history"})
VALID_CONFIDENCE_LEVELS = frozenset({"confirmed", "likely", "uncertain", "speculative"})


def init_schema(conn):
    """Create fragments, tree_branches, fragment_lattice_cells. Idempotent."""
    cur = conn.cursor()
    cur.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    cur.execute(f"SET search_path = {SCHEMA}, public")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS fragments (
            id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            person_name      TEXT NOT NULL,
            date_ref         TEXT,
            story_text       TEXT,
            photo_ref        TEXT,
            source           TEXT,
            fragment_type    TEXT NOT NULL
                CHECK (fragment_type IN ('name','date','story','photo','document','oral_history')),
            confidence       TEXT NOT NULL DEFAULT 'uncertain'
                CHECK (confidence IN ('confirmed','likely','uncertain','speculative')),
            binder_synced_at TIMESTAMP,
            created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_deleted       INTEGER DEFAULT 0
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS tree_branches (
            id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            root_ancestor    TEXT NOT NULL,
            generation_depth INTEGER NOT NULL,
            confirmed_count  INTEGER DEFAULT 0,
            fragment_ids     INTEGER[],
            created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS fragment_lattice_cells (
            id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            fragment_id  BIGINT NOT NULL REFERENCES fragments(id),
            domain       TEXT NOT NULL,
            depth        INTEGER NOT NULL CHECK (depth >= 1 AND depth <= 23),
            temporal     TEXT NOT NULL,
            content      TEXT NOT NULL,
            source       TEXT,
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_sensitive BOOLEAN DEFAULT FALSE,
            UNIQUE(fragment_id, domain, depth, temporal)
        )
    """)

    cur.execute("CREATE INDEX IF NOT EXISTS idx_fragments_person ON fragments (person_name)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_fragments_type ON fragments (fragment_type)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_fragments_confidence ON fragments (confidence)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_branches_ancestor ON tree_branches (root_ancestor)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_flc_fragment ON fragment_lattice_cells (fragment_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_flc_domain ON fragment_lattice_cells (domain)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_flc_temporal ON fragment_lattice_cells (temporal)")

    conn.commit()


def add_fragment(conn, *, person_name: str, fragment_type: str, confidence: str = "uncertain",
                 date_ref: str = None, story_text: str = None, photo_ref: str = None,
                 source: str = None) -> Dict[str, Any]:
    """Insert a family fragment. Returns the new row as a dict."""
    _gate.authorized("write")
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
    _gate.authorized("write")
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
                     content: str, source: str = None, is_sensitive: bool = False) -> Dict[str, Any]:
    """Map a fragment to a lattice cell. Upserts on (fragment_id, domain, depth, temporal)."""
    _gate.authorized("write")
    _validate_lattice(domain, depth, temporal)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO fragment_lattice_cells
            (fragment_id, domain, depth, temporal, content, source, is_sensitive)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (fragment_id, domain, depth, temporal)
        DO UPDATE SET content = EXCLUDED.content,
                      source = EXCLUDED.source,
                      is_sensitive = EXCLUDED.is_sensitive
        RETURNING id, fragment_id, domain, depth, temporal, content, source, created_at, is_sensitive
    """, (fragment_id, domain, depth, temporal, content, source, is_sensitive))
    row = cur.fetchone()
    cols = [d[0] for d in cur.description]
    conn.commit()
    return dict(zip(cols, row))


def search_fragments(conn, query: str, fragment_type: str = None) -> List[Dict[str, Any]]:
    """Search fragments by person_name or story_text. Optionally filter by type."""
    _gate.authorized("read")
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
            WHERE (person_name ILIKE %s OR story_text ILIKE %s) AND is_deleted = 0
            ORDER BY created_at DESC
        """, (f"%{query}%", f"%{query}%"))
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in rows]


def get_unsynced_fragments(conn, limit: int = 100) -> List[Dict[str, Any]]:
    """Return fragments not yet synced to the Binder."""
    _gate.authorized("read")
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
    """Return all branches for a given root ancestor."""
    _gate.authorized("read")
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM tree_branches
        WHERE root_ancestor ILIKE %s
        ORDER BY generation_depth ASC
    """, (f"%{root_ancestor}%",))
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in rows]
