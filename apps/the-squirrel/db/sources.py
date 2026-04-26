"""
db.sources — System layer: source_registry.
Schema: the_squirrel

User-agnostic. No PII. No SAP gate required.
Stores genealogy source providers — community archives, databases, platforms.
FTS via tsvector for location-based lookup.

Seeded from data/community_history_archives.json (779 entries, 43 states).
Query with lookup_sources(query, state).
"""

import json
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Optional
from db import SCHEMA

DATA_DIR = Path(__file__).parent.parent / "data"
CHA_JSON = DATA_DIR / "community_history_archives.json"

VALID_PROVIDERS = frozenset({
    "community_history_archives",
    "familysearch",
    "findagrave",
    "courtlistener",
    "ancestry",
    "newspapers_com",
    "fold3",
    "other",
})


def init_schema(conn):
    """Create source_registry table with GIN FTS index. Idempotent."""
    cur = conn.cursor()
    cur.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    cur.execute(f"SET search_path = {SCHEMA}, public")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS source_registry (
            id            TEXT PRIMARY KEY,
            name          TEXT NOT NULL,
            state         TEXT,
            url           TEXT NOT NULL,
            provider      TEXT NOT NULL DEFAULT 'community_history_archives',
            coverage      JSONB,
            search_vector tsvector GENERATED ALWAYS AS (
                to_tsvector('english',
                    coalesce(name, '') || ' ' || coalesce(state, '')
                )
            ) STORED,
            created_at    TIMESTAMPTZ DEFAULT now(),
            ratified      BOOLEAN DEFAULT FALSE
        )
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_source_registry_fts
        ON source_registry USING gin(search_vector)
    """)
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_source_registry_state ON source_registry (state)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_source_registry_provider ON source_registry (provider)"
    )

    conn.commit()


def _gen_id(name: str, state: str) -> str:
    """Deterministic BASE17 ID from name+state for idempotent seeding."""
    ALPHABET = "0123456789ACEHKLNRTXZ"
    h = hashlib.sha1(f"{state}::{name}".encode()).digest()
    n = int.from_bytes(h[:5], "big")
    result = []
    for _ in range(8):
        result.append(ALPHABET[n % 21])
        n //= 21
    return "".join(reversed(result))


def seed_from_json(conn, json_path: Path = CHA_JSON, ratify: bool = False) -> int:
    """
    Bulk-insert community archives from JSON. Idempotent (ON CONFLICT DO NOTHING).
    Returns count of newly inserted rows.
    """
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)
    entries = data["archives"] if isinstance(data, dict) else data

    cur = conn.cursor()
    inserted = 0
    for entry in entries:
        row_id = _gen_id(entry["name"], entry.get("state", ""))
        cur.execute("""
            INSERT INTO source_registry (id, name, state, url, provider, ratified)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING
        """, (row_id, entry["name"], entry.get("state"), entry["url"],
              "community_history_archives", ratify))
        inserted += cur.rowcount

    conn.commit()
    return inserted


def lookup_sources(conn, query: str = "", state: str = None,
                   provider: str = None, limit: int = 10) -> List[Dict[str, Any]]:
    """
    FTS lookup for source providers.

    Args:
        query:    Free-text — city, county, archive name, region.
        state:    Optional state filter (name or abbreviation, ILIKE).
        provider: Optional provider filter (exact match).
        limit:    Max results.

    Returns list of dicts: {id, name, state, url, provider, ratified}
    """
    cur = conn.cursor()
    conditions = []
    params = []

    if query.strip():
        conditions.append("search_vector @@ plainto_tsquery('english', %s)")
        params.append(query)

    if state:
        conditions.append("state ILIKE %s")
        params.append(f"%{state}%")

    if provider:
        conditions.append("provider = %s")
        params.append(provider)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    if query.strip():
        order = "ORDER BY ts_rank(search_vector, plainto_tsquery('english', %s)) DESC"
        params.append(query)
    else:
        order = "ORDER BY name ASC"

    cur.execute(f"""
        SELECT id, name, state, url, provider, ratified
        FROM source_registry
        {where}
        {order}
        LIMIT %s
    """, params + [limit])

    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in rows]


def add_source(conn, *, name: str, url: str, state: str = None,
               provider: str = "other", coverage: dict = None,
               ratified: bool = False) -> Dict[str, Any]:
    """Add or update a single source provider entry."""
    if provider not in VALID_PROVIDERS:
        raise ValueError(f"Invalid provider '{provider}'. Must be one of: {VALID_PROVIDERS}")
    row_id = _gen_id(name, state or "")
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO source_registry (id, name, state, url, provider, coverage, ratified)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET
            url      = EXCLUDED.url,
            provider = EXCLUDED.provider,
            coverage = EXCLUDED.coverage,
            ratified = EXCLUDED.ratified
        RETURNING id, name, state, url, provider, coverage, created_at, ratified
    """, (row_id, name, state, url, provider,
          json.dumps(coverage) if coverage else None, ratified))
    row = cur.fetchone()
    cols = [d[0] for d in cur.description]
    conn.commit()
    return dict(zip(cols, row))
