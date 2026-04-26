"""
sources_db.py -- Citation/source tracking database using the 23-cubed lattice structure.

PostgreSQL-only. Schema: source_trail.
Each source maps into a 23x23x23 lattice (12,167 cells per entity).

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
    """Return a pooled Postgres connection with search_path = source_trail, public."""
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
    """Convert a cursor row to an immutable-style dict. Returns None if row is None."""
    if row is None:
        return None
    cols = [d[0] for d in cur.description]
    return dict(zip(cols, row))


def _rows_to_dicts(cur, rows) -> List[Dict[str, Any]]:
    """Convert cursor rows to a list of dicts."""
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
        CREATE TABLE IF NOT EXISTS lattice_cells (
            id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            source_id     BIGINT NOT NULL REFERENCES sources(id),
            domain        TEXT NOT NULL,
            depth         INTEGER NOT NULL CHECK (depth >= 1 AND depth <= 23),
            temporal      TEXT NOT NULL,
            content       TEXT NOT NULL,
            source_ref    TEXT,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_sensitive  INTEGER DEFAULT 0,
            UNIQUE(source_id, domain, depth, temporal)
        )
    """)

    # Indices
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sources_title ON sources (title)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sources_type ON sources (source_type)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sources_domain ON sources (domain_name)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sources_url ON sources (url)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_citations_source ON citations (source_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_citations_doc ON citations (cited_in_document)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_links_a ON source_links (source_a)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_links_b ON source_links (source_b)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_lc_source ON lattice_cells (source_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_lc_domain ON lattice_cells (domain)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_lc_temporal ON lattice_cells (temporal)")

    conn.commit()


# ---------------------------------------------------------------------------
# CRUD -- all return new dicts (immutable pattern)
# ---------------------------------------------------------------------------

def add_source(conn, *, title: str, source_type: str, url: str = None,
               authors: List[str] = None, publication_date: str = None,
               access_date: str = None, domain_name: str = None) -> Dict[str, Any]:
    """Insert a source. Returns a dict with the new row (including id)."""
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
    """Attach a citation record to a source. Returns the new row as a dict."""
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
    """Link two sources. Returns the new link row as a dict.
    Raises on duplicate (source_a, source_b, link_type)."""
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


def place_in_lattice(conn, source_id: int, domain: str, depth: int, temporal: str,
                     content: str, source_ref: str = None,
                     is_sensitive: bool = False) -> Dict[str, Any]:
    """Map a source to a lattice cell. Upserts on (source_id, domain, depth, temporal).
    Returns the cell row as a dict."""
    _validate_lattice(domain, depth, temporal)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO lattice_cells (source_id, domain, depth, temporal, content,
                                   source_ref, is_sensitive)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (source_id, domain, depth, temporal)
        DO UPDATE SET content = EXCLUDED.content,
                      source_ref = EXCLUDED.source_ref,
                      is_sensitive = EXCLUDED.is_sensitive
        RETURNING id, source_id, domain, depth, temporal, content, source_ref,
                  created_at, is_sensitive
    """, (source_id, domain, depth, temporal, content, source_ref,
          1 if is_sensitive else 0))
    result = _row_to_dict(cur, cur.fetchone())
    conn.commit()
    return result


def verify_source(conn, source_id: int) -> Dict[str, Any]:
    """Check the source URL via HTTP HEAD request. Updates is_verified, last_checked,
    http_status. Returns the updated source row as a dict."""
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
            is_verified = False
        except (urllib.error.URLError, OSError):
            http_status = None
            is_verified = False

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
    """Search sources by title/URL (case-insensitive ILIKE). Returns list of dicts."""
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
    cur.execute(f"""
        SELECT * FROM sources
        WHERE {where}
        ORDER BY title
    """, params)
    return _rows_to_dicts(cur, cur.fetchall())


def get_citation_chain(conn, source_id: int, max_depth: int = 5) -> Dict[str, Any]:
    """Walk the source_links graph starting from source_id up to max_depth hops.
    Returns a dict with 'root' (source dict), 'nodes' (all visited sources),
    and 'edges' (all traversed links). BFS traversal."""
    cur = conn.cursor()

    # Fetch root
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

    # Deduplicate edges by id
    seen_edge_ids = set()
    unique_edges = []
    for e in all_edges:
        if e["id"] not in seen_edge_ids:
            seen_edge_ids.add(e["id"])
            unique_edges.append(e)

    return {"root": root, "nodes": all_nodes, "edges": unique_edges}
