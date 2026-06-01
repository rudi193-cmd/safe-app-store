"""
legal_db.py -- Legal case tracking database using the 23-cubed lattice structure.

PostgreSQL-only. Schema: legal_gazelle.
Each case maps into a 23x23x23 lattice (12,167 cells per case).

Lattice constants imported from Willow's user_lattice.py.
DB connection follows Willow's genealogy_db.py pattern (psycopg2, pooled).
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

SCHEMA = "legal_gazelle"

VALID_CASE_TYPES = frozenset({"workers_comp", "bankruptcy", "mediation", "other"})
VALID_CASE_STATUSES = frozenset({"open", "closed", "pending", "resolved"})
VALID_DOC_TYPES = frozenset({"filing", "correspondence", "medical", "research", "evidence"})
VALID_EVENT_TYPES = frozenset({"hearing", "deadline", "filing", "mediation", "decision"})


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
    """Return a pooled Postgres connection with search_path = legal_gazelle, public."""
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


def _validate_case_type(case_type: str):
    if case_type not in VALID_CASE_TYPES:
        raise ValueError(f"Invalid case_type '{case_type}'. Must be one of: {VALID_CASE_TYPES}")


def _validate_case_status(status: str):
    if status not in VALID_CASE_STATUSES:
        raise ValueError(f"Invalid status '{status}'. Must be one of: {VALID_CASE_STATUSES}")


def _validate_doc_type(doc_type: str):
    if doc_type not in VALID_DOC_TYPES:
        raise ValueError(f"Invalid doc_type '{doc_type}'. Must be one of: {VALID_DOC_TYPES}")


def _validate_event_type(event_type: str):
    if event_type not in VALID_EVENT_TYPES:
        raise ValueError(f"Invalid event_type '{event_type}'. Must be one of: {VALID_EVENT_TYPES}")


# ---------------------------------------------------------------------------
# Schema init
# ---------------------------------------------------------------------------

def init_schema(conn):
    """Create the legal_gazelle schema and all tables. Idempotent."""
    cur = conn.cursor()

    cur.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    cur.execute(f"SET search_path = {SCHEMA}, public")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS cases (
            id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            case_number   TEXT UNIQUE,
            case_type     TEXT NOT NULL CHECK (case_type IN ('workers_comp','bankruptcy','mediation','other')),
            title         TEXT NOT NULL,
            status        TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','closed','pending','resolved')),
            jurisdiction  TEXT,
            filed_date    TEXT,
            description   TEXT,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_deleted    BOOLEAN DEFAULT FALSE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            case_id         BIGINT NOT NULL REFERENCES cases(id),
            doc_type        TEXT NOT NULL CHECK (doc_type IN ('filing','correspondence','medical','research','evidence')),
            title           TEXT NOT NULL,
            source_url      TEXT,
            content_summary TEXT,
            filed_date      TEXT,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            case_id       BIGINT NOT NULL REFERENCES cases(id),
            event_type    TEXT NOT NULL CHECK (event_type IN ('hearing','deadline','filing','mediation','decision')),
            event_date    TEXT,
            description   TEXT,
            is_completed  BOOLEAN DEFAULT FALSE,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS lattice_cells (
            id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            case_id       BIGINT NOT NULL REFERENCES cases(id),
            domain        TEXT NOT NULL,
            depth         INTEGER NOT NULL CHECK (depth >= 1 AND depth <= 23),
            temporal      TEXT NOT NULL,
            content       TEXT NOT NULL,
            source        TEXT,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_sensitive  BOOLEAN DEFAULT FALSE,
            UNIQUE(case_id, domain, depth, temporal)
        )
    """)

    # Indices
    cur.execute("CREATE INDEX IF NOT EXISTS idx_cases_number ON cases (case_number)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_cases_type ON cases (case_type)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_cases_status ON cases (status)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_docs_case ON documents (case_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_docs_type ON documents (doc_type)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_events_case ON events (case_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_events_date ON events (event_date)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_lc_case ON lattice_cells (case_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_lc_domain ON lattice_cells (domain)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_lc_temporal ON lattice_cells (temporal)")

    conn.commit()


# ---------------------------------------------------------------------------
# CRUD -- all return new dicts (immutable pattern)
# ---------------------------------------------------------------------------

def add_case(conn, *, case_number: str = None, case_type: str, title: str,
             status: str = "open", jurisdiction: str = None, filed_date: str = None,
             description: str = None) -> Dict[str, Any]:
    """Insert a case. Returns a dict with the new row (including id)."""
    _validate_case_type(case_type)
    _validate_case_status(status)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO cases (case_number, case_type, title, status, jurisdiction, filed_date, description)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id, case_number, case_type, title, status, jurisdiction, filed_date,
                  description, created_at, updated_at, is_deleted
    """, (case_number, case_type, title, status, jurisdiction, filed_date, description))
    row = cur.fetchone()
    cols = [d[0] for d in cur.description]
    conn.commit()
    return dict(zip(cols, row))


def add_document(conn, *, case_id: int, doc_type: str, title: str,
                 source_url: str = None, content_summary: str = None,
                 filed_date: str = None) -> Dict[str, Any]:
    """Attach a document to a case. Returns the new document row as a dict."""
    _validate_doc_type(doc_type)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO documents (case_id, doc_type, title, source_url, content_summary, filed_date)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id, case_id, doc_type, title, source_url, content_summary, filed_date, created_at
    """, (case_id, doc_type, title, source_url, content_summary, filed_date))
    row = cur.fetchone()
    cols = [d[0] for d in cur.description]
    conn.commit()
    return dict(zip(cols, row))


def add_event(conn, *, case_id: int, event_type: str, event_date: str = None,
              description: str = None, is_completed: bool = False) -> Dict[str, Any]:
    """Add an event to a case. Returns the new event row as a dict."""
    _validate_event_type(event_type)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO events (case_id, event_type, event_date, description, is_completed)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id, case_id, event_type, event_date, description, is_completed, created_at
    """, (case_id, event_type, event_date, description, is_completed))
    row = cur.fetchone()
    cols = [d[0] for d in cur.description]
    conn.commit()
    return dict(zip(cols, row))


def place_in_lattice(conn, case_id: int, domain: str, depth: int, temporal: str,
                     content: str, source: str = None, is_sensitive: bool = False) -> Dict[str, Any]:
    """Map a case to a lattice cell. Upserts on (case_id, domain, depth, temporal).
    Returns the cell row as a dict."""
    _validate_lattice(domain, depth, temporal)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO lattice_cells (case_id, domain, depth, temporal, content, source, is_sensitive)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (case_id, domain, depth, temporal)
        DO UPDATE SET content = EXCLUDED.content, source = EXCLUDED.source, is_sensitive = EXCLUDED.is_sensitive
        RETURNING id, case_id, domain, depth, temporal, content, source, created_at, is_sensitive
    """, (case_id, domain, depth, temporal, content, source, is_sensitive))
    row = cur.fetchone()
    cols = [d[0] for d in cur.description]
    conn.commit()
    return dict(zip(cols, row))


def get_case_timeline(conn, case_id: int) -> Dict[str, Any]:
    """Return the case record plus all documents and events, ordered by date. Immutable result."""
    cur = conn.cursor()

    cur.execute("SELECT * FROM cases WHERE id = %s AND is_deleted = FALSE", (case_id,))
    case_row = cur.fetchone()
    if case_row is None:
        return {"case": None, "documents": [], "events": []}
    ccols = [d[0] for d in cur.description]
    case = dict(zip(ccols, case_row))

    cur.execute("""
        SELECT * FROM documents WHERE case_id = %s ORDER BY filed_date ASC NULLS LAST, created_at ASC
    """, (case_id,))
    doc_rows = cur.fetchall()
    dcols = [d[0] for d in cur.description]
    documents = [dict(zip(dcols, r)) for r in doc_rows]

    cur.execute("""
        SELECT * FROM events WHERE case_id = %s ORDER BY event_date ASC NULLS LAST, created_at ASC
    """, (case_id,))
    evt_rows = cur.fetchall()
    ecols = [d[0] for d in cur.description]
    events = [dict(zip(ecols, r)) for r in evt_rows]

    return {"case": case, "documents": documents, "events": events}


def search_cases(conn, query: str, case_type: str = None, status: str = None) -> List[Dict[str, Any]]:
    """Search cases by title/description (ILIKE) with optional filters. Returns list of dicts."""
    cur = conn.cursor()
    conditions = ["is_deleted = FALSE", "(title ILIKE %s OR description ILIKE %s)"]
    params: list = [f"%{query}%", f"%{query}%"]

    if case_type is not None:
        _validate_case_type(case_type)
        conditions.append("case_type = %s")
        params.append(case_type)

    if status is not None:
        _validate_case_status(status)
        conditions.append("status = %s")
        params.append(status)

    where = " AND ".join(conditions)
    cur.execute(f"""
        SELECT * FROM cases WHERE {where} ORDER BY updated_at DESC
    """, params)
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in rows]
