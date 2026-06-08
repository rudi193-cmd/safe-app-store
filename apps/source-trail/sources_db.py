"""
sources_db.py -- Citation/source tracking database for the Source Trail app.

PostgreSQL only. Schema: source_trail.
Tables: sources, citations, source_links, verified_claims.

Connection: mirrors pg_bridge.py — Unix socket by default (peer auth).
Env vars: WILLOW_PG_DB, WILLOW_PG_USER, WILLOW_PG_HOST, WILLOW_PG_PORT.
"""

import os
import threading
from datetime import datetime
from typing import Optional, List, Dict, Any

# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

_pool = None
_pool_lock = threading.Lock()

SCHEMA = "source_trail"

VALID_SOURCE_TYPES = frozenset({
    "article", "paper", "book", "website", "government",
    "dataset", "video", "podcast", "other",
})

VALID_CITATION_FORMATS = frozenset({
    "apa", "mla", "chicago", "bibtex", "raw",
})

VALID_LINK_TYPES = frozenset({
    "cites", "cited_by", "related", "contradicts", "supports", "updates",
})


def _get_pool():
    global _pool
    if _pool is not None:
        return _pool
    with _pool_lock:
        if _pool is None:
            import psycopg2
            import psycopg2.pool
            # Mirror pg_bridge.py: omit host → Unix socket → peer auth, no password.
            # WILLOW_PG_HOST can force TCP if needed.
            _pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=1,
                maxconn=10,
                dbname=os.environ.get("WILLOW_PG_DB", "willow_20"),
                user=os.environ.get("WILLOW_PG_USER", os.environ.get("USER", "")),
                host=os.environ.get("WILLOW_PG_HOST") or None,
                port=os.environ.get("WILLOW_PG_PORT") or None,
            )
    return _pool


def get_connection():
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
    try:
        conn.rollback()
    except Exception:
        pass
    _get_pool().putconn(conn)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate_source_type(source_type: str):
    if source_type not in VALID_SOURCE_TYPES:
        raise ValueError(f"Invalid source_type '{source_type}'. Must be one of: {VALID_SOURCE_TYPES}")


def _validate_citation_format(fmt: str):
    if fmt not in VALID_CITATION_FORMATS:
        raise ValueError(f"Invalid citation_format '{fmt}'. Must be one of: {VALID_CITATION_FORMATS}")


def _validate_link_type(link_type: str):
    if link_type not in VALID_LINK_TYPES:
        raise ValueError(f"Invalid link_type '{link_type}'. Must be one of: {VALID_LINK_TYPES}")


def _row_to_dict(cur, row) -> Optional[Dict[str, Any]]:
    if row is None:
        return None
    cols = [d[0] for d in cur.description]
    return dict(zip(cols, row))


def _rows_to_dicts(cur, rows) -> List[Dict[str, Any]]:
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in rows]


# ---------------------------------------------------------------------------
# Schema init
# ---------------------------------------------------------------------------

def init_schema(conn):
    """Create the source_trail schema and all tables. Idempotent."""
    cur = conn.cursor()

    cur.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    cur.execute(f"SET search_path = {SCHEMA}, public")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sources (
            id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            url               TEXT,
            title             TEXT NOT NULL,
            authors           TEXT[],
            publication_date  TEXT,
            access_date       TEXT,
            source_type       TEXT NOT NULL CHECK (source_type IN (
                'article','paper','book','website','government',
                'dataset','video','podcast','other'
            )),
            domain_name       TEXT,
            is_verified       BOOLEAN DEFAULT FALSE,
            last_checked      TIMESTAMP,
            http_status       INTEGER,
            created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_deleted        INTEGER DEFAULT 0
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS citations (
            id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            source_id         BIGINT NOT NULL REFERENCES sources(id),
            cited_in_document TEXT NOT NULL,
            page_ref          TEXT,
            context_quote     TEXT,
            citation_format   TEXT NOT NULL CHECK (citation_format IN (
                'apa','mla','chicago','bibtex','raw'
            )),
            created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS source_links (
            id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            source_a    BIGINT NOT NULL REFERENCES sources(id),
            source_b    BIGINT NOT NULL REFERENCES sources(id),
            link_type   TEXT NOT NULL CHECK (link_type IN (
                'cites','cited_by','related','contradicts','supports','updates'
            )),
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(source_a, source_b, link_type)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS verified_claims (
            id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            claim_text    TEXT NOT NULL,
            matched       BOOLEAN NOT NULL DEFAULT FALSE,
            title         TEXT,
            url           TEXT,
            date          TEXT,
            source        TEXT,
            tier          TEXT,
            confidence    REAL,
            document_ref  TEXT,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("CREATE INDEX IF NOT EXISTS idx_sources_title ON sources (title)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sources_type ON sources (source_type)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sources_domain ON sources (domain_name)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sources_url ON sources (url)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_citations_source ON citations (source_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_citations_doc ON citations (cited_in_document)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_links_a ON source_links (source_a)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_links_b ON source_links (source_b)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_vc_document ON verified_claims (document_ref)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_vc_matched ON verified_claims (matched)")

    conn.commit()


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def add_source(conn, *, title: str, source_type: str, url: str = None,
               authors: List[str] = None, publication_date: str = None,
               access_date: str = None, domain_name: str = None) -> Dict[str, Any]:
    _validate_source_type(source_type)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO sources (url, title, authors, publication_date, access_date,
                             source_type, domain_name)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id, url, title, authors, publication_date, access_date, source_type,
                  domain_name, is_verified, last_checked, http_status,
                  created_at, updated_at, is_deleted
    """, (url, title, authors, publication_date, access_date, source_type, domain_name))
    result = _row_to_dict(cur, cur.fetchone())
    conn.commit()
    return result


def add_citation(conn, *, source_id: int, cited_in_document: str,
                 citation_format: str, page_ref: str = None,
                 context_quote: str = None) -> Dict[str, Any]:
    _validate_citation_format(citation_format)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO citations (source_id, cited_in_document, page_ref,
                               context_quote, citation_format)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id, source_id, cited_in_document, page_ref, context_quote,
                  citation_format, created_at
    """, (source_id, cited_in_document, page_ref, context_quote, citation_format))
    result = _row_to_dict(cur, cur.fetchone())
    conn.commit()
    return result


def add_link(conn, *, source_a: int, source_b: int, link_type: str) -> Dict[str, Any]:
    _validate_link_type(link_type)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO source_links (source_a, source_b, link_type)
        VALUES (%s, %s, %s)
        RETURNING id, source_a, source_b, link_type, created_at
    """, (source_a, source_b, link_type))
    result = _row_to_dict(cur, cur.fetchone())
    conn.commit()
    return result


def store_verified_claim(conn, *, claim_text: str, matched: bool,
                         title: str = None, url: str = None, date: str = None,
                         source: str = None, tier: str = None,
                         confidence: float = None,
                         document_ref: str = None) -> Dict[str, Any]:
    """Persist one result row from source_trail_verify."""
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO verified_claims
            (claim_text, matched, title, url, date, source, tier, confidence, document_ref)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id, claim_text, matched, title, url, date, source, tier,
                  confidence, document_ref, created_at
    """, (claim_text, matched, title, url, date, source, tier, confidence, document_ref))
    result = _row_to_dict(cur, cur.fetchone())
    conn.commit()
    return result


def search_verified_claims(conn, query: str = None, document_ref: str = None,
                           matched_only: bool = False,
                           limit: int = 50) -> List[Dict[str, Any]]:
    """Search stored verified claims by text or document_ref."""
    conditions = []
    params: list = []

    if query:
        conditions.append("claim_text ILIKE %s")
        params.append(f"%{query}%")
    if document_ref:
        conditions.append("document_ref = %s")
        params.append(document_ref)
    if matched_only:
        conditions.append("matched = TRUE")

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    params.append(limit)

    cur = conn.cursor()
    cur.execute(f"""
        SELECT * FROM verified_claims
        {where}
        ORDER BY created_at DESC
        LIMIT %s
    """, params)
    return _rows_to_dicts(cur, cur.fetchall())


def verify_source(conn, source_id: int) -> Dict[str, Any]:
    """Check the source URL via HTTP HEAD. Updates is_verified, last_checked, http_status."""
    import urllib.request
    import urllib.error

    cur = conn.cursor()
    cur.execute("SELECT id, url FROM sources WHERE id = %s AND is_deleted = 0", (source_id,))
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"Source {source_id} not found or deleted")

    url = row[1]
    http_status = None
    is_verified = False

    if url:
        try:
            req = urllib.request.Request(url, method="HEAD")
            req.add_header("User-Agent", "SAFE-SourceTrail/1.0")
            with urllib.request.urlopen(req, timeout=10) as resp:
                http_status = resp.status
                is_verified = 200 <= http_status < 400
        except urllib.error.HTTPError as e:
            http_status = e.code
        except (urllib.error.URLError, OSError):
            pass

    now = datetime.utcnow()
    cur.execute("""
        UPDATE sources
        SET is_verified = %s, last_checked = %s, http_status = %s, updated_at = %s
        WHERE id = %s
        RETURNING id, url, title, authors, publication_date, access_date, source_type,
                  domain_name, is_verified, last_checked, http_status,
                  created_at, updated_at, is_deleted
    """, (is_verified, now, http_status, now, source_id))
    result = _row_to_dict(cur, cur.fetchone())
    conn.commit()
    return result


def search_sources(conn, query: str, source_type: str = None,
                   verified_only: bool = False) -> List[Dict[str, Any]]:
    conditions = ["is_deleted = 0", "(title ILIKE %s OR url ILIKE %s)"]
    params: list = [f"%{query}%", f"%{query}%"]

    if source_type is not None:
        _validate_source_type(source_type)
        conditions.append("source_type = %s")
        params.append(source_type)
    if verified_only:
        conditions.append("is_verified = TRUE")

    where = " AND ".join(conditions)
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM sources WHERE {where} ORDER BY title", params)
    return _rows_to_dicts(cur, cur.fetchall())


def get_citation_chain(conn, source_id: int, max_depth: int = 5) -> Dict[str, Any]:
    """BFS walk of source_links from source_id up to max_depth hops."""
    cur = conn.cursor()
    cur.execute("SELECT * FROM sources WHERE id = %s AND is_deleted = 0", (source_id,))
    root_row = cur.fetchone()
    if root_row is None:
        return {"root": None, "nodes": [], "edges": []}
    root_cols = [d[0] for d in cur.description]
    root = dict(zip(root_cols, root_row))

    visited = {source_id}
    frontier = [source_id]
    all_nodes = [root]
    all_edges: List[Dict[str, Any]] = []

    for _ in range(max_depth):
        if not frontier:
            break
        placeholders = ",".join(["%s"] * len(frontier))
        cur.execute(f"""
            SELECT * FROM source_links
            WHERE source_a IN ({placeholders}) OR source_b IN ({placeholders})
        """, frontier + frontier)
        link_rows = cur.fetchall()
        link_cols = [d[0] for d in cur.description]

        next_frontier = []
        for lr in link_rows:
            link = dict(zip(link_cols, lr))
            all_edges.append(link)
            for neighbor_id in (link["source_a"], link["source_b"]):
                if neighbor_id not in visited:
                    visited.add(neighbor_id)
                    next_frontier.append(neighbor_id)

        if next_frontier:
            placeholders = ",".join(["%s"] * len(next_frontier))
            cur.execute(f"""
                SELECT * FROM sources
                WHERE id IN ({placeholders}) AND is_deleted = 0
            """, next_frontier)
            node_rows = cur.fetchall()
            node_cols = [d[0] for d in cur.description]
            all_nodes.extend(dict(zip(node_cols, nr)) for nr in node_rows)

        frontier = next_frontier

    seen_edge_ids: set = set()
    unique_edges = []
    for e in all_edges:
        if e["id"] not in seen_edge_ids:
            seen_edge_ids.add(e["id"])
            unique_edges.append(e)

    return {"root": root, "nodes": all_nodes, "edges": unique_edges}
