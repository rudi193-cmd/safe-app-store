"""
db.persons — PII layer: persons, relationships, person_lattice_cells, person_sources.
Schema: the_squirrel

Persons are fully-resolved individuals in the family tree.
Fragments (db.fragments) are raw observations; persons are what the Binder promotes them to.

SAP gate (L3-R15): all write functions call sap.core.gate.authorized() before touching PII.
Reads (search_persons, get_family_tree) are gated on "read" for symmetry.
init_schema() is DDL — no PII, no gate.
"""

from typing import Dict, Any, List
from db import _validate_lattice, SCHEMA
import sap.core.gate as _gate

VALID_RELATIONSHIP_TYPES = frozenset({"parent", "child", "spouse", "sibling"})
VALID_SOURCE_TYPES = frozenset({"findagrave", "familysearch", "census", "document", "oral"})


def init_schema(conn):
    """Create persons, relationships, person_lattice_cells, person_sources. Idempotent."""
    cur = conn.cursor()
    cur.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    cur.execute(f"SET search_path = {SCHEMA}, public")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS persons (
            id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            full_name    TEXT NOT NULL,
            birth_date   TEXT,
            birth_place  TEXT,
            death_date   TEXT,
            death_place  TEXT,
            burial_place TEXT,
            memorial_id  TEXT,
            memorial_url TEXT,
            bio          TEXT,
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_deleted   BOOLEAN DEFAULT FALSE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS relationships (
            id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            person_id         BIGINT NOT NULL REFERENCES persons(id),
            related_person_id BIGINT NOT NULL REFERENCES persons(id),
            relationship_type TEXT NOT NULL
                CHECK (relationship_type IN ('parent','child','spouse','sibling')),
            created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS person_lattice_cells (
            id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            person_id    BIGINT NOT NULL REFERENCES persons(id),
            domain       TEXT NOT NULL,
            depth        INTEGER NOT NULL CHECK (depth >= 1 AND depth <= 23),
            temporal     TEXT NOT NULL,
            content      TEXT NOT NULL,
            source       TEXT,
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_sensitive BOOLEAN DEFAULT FALSE,
            UNIQUE(person_id, domain, depth, temporal)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS person_sources (
            id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            person_id    BIGINT NOT NULL REFERENCES persons(id),
            source_type  TEXT NOT NULL
                CHECK (source_type IN ('findagrave','familysearch','census','document','oral')),
            source_url   TEXT,
            source_title TEXT,
            raw_content  TEXT,
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("CREATE INDEX IF NOT EXISTS idx_persons_name ON persons (full_name)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_rel_person ON relationships (person_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_rel_related ON relationships (related_person_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_plc_person ON person_lattice_cells (person_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_plc_domain ON person_lattice_cells (domain)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_plc_temporal ON person_lattice_cells (temporal)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_psrc_person ON person_sources (person_id)")

    conn.commit()


def add_person(conn, *, full_name: str, birth_date: str = None, birth_place: str = None,
               death_date: str = None, death_place: str = None, burial_place: str = None,
               memorial_id: str = None, memorial_url: str = None, bio: str = None) -> Dict[str, Any]:
    """Insert a person. Returns the new row as a dict."""
    _gate.authorized("write")
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
    _gate.authorized("write")
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
    """Attach a source record to a person. Returns the new source row as a dict."""
    _gate.authorized("write")
    if source_type not in VALID_SOURCE_TYPES:
        raise ValueError(f"Invalid source_type '{source_type}'. Must be one of: {VALID_SOURCE_TYPES}")
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO person_sources (person_id, source_type, source_url, source_title, raw_content)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id, person_id, source_type, source_url, source_title, raw_content, created_at
    """, (person_id, source_type, url, title, content))
    row = cur.fetchone()
    cols = [d[0] for d in cur.description]
    conn.commit()
    return dict(zip(cols, row))


def place_in_lattice(conn, person_id: int, domain: str, depth: int, temporal: str,
                     content: str, source: str = None, is_sensitive: bool = False) -> Dict[str, Any]:
    """Map a person to a lattice cell. Upserts on (person_id, domain, depth, temporal)."""
    _gate.authorized("write")
    _validate_lattice(domain, depth, temporal)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO person_lattice_cells
            (person_id, domain, depth, temporal, content, source, is_sensitive)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (person_id, domain, depth, temporal)
        DO UPDATE SET content = EXCLUDED.content,
                      source = EXCLUDED.source,
                      is_sensitive = EXCLUDED.is_sensitive
        RETURNING id, person_id, domain, depth, temporal, content, source, created_at, is_sensitive
    """, (person_id, domain, depth, temporal, content, source, is_sensitive))
    row = cur.fetchone()
    cols = [d[0] for d in cur.description]
    conn.commit()
    return dict(zip(cols, row))


def get_family_tree(conn, person_id: int) -> Dict[str, Any]:
    """Return the person record plus all relationships. Immutable result."""
    _gate.authorized("read")
    cur = conn.cursor()
    cur.execute("SELECT * FROM persons WHERE id = %s AND is_deleted = FALSE", (person_id,))
    person_row = cur.fetchone()
    if person_row is None:
        return {"person": None, "relationships": []}
    pcols = [d[0] for d in cur.description]
    person = dict(zip(pcols, person_row))

    cur.execute("""
        SELECT r.*, p.full_name AS related_name
        FROM relationships r JOIN persons p ON p.id = r.related_person_id
        WHERE r.person_id = %s
        UNION ALL
        SELECT r.*, p.full_name AS related_name
        FROM relationships r JOIN persons p ON p.id = r.person_id
        WHERE r.related_person_id = %s
    """, (person_id, person_id))
    rows = cur.fetchall()
    rcols = [d[0] for d in cur.description]
    return {"person": person, "relationships": [dict(zip(rcols, r)) for r in rows]}


def search_persons(conn, name_query: str) -> List[Dict[str, Any]]:
    """Search persons by name (case-insensitive ILIKE). Returns list of dicts."""
    _gate.authorized("read")
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM persons
        WHERE full_name ILIKE %s AND is_deleted = FALSE
        ORDER BY full_name
    """, (f"%{name_query}%",))
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in rows]
