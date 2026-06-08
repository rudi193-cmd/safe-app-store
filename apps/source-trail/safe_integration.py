"""
SAFE Framework Integration — Source Trail

verify(text) → calls core/source_trail.py (via WILLOW_ROOT) → stores results
               in verified_claims via sources_db.

query(q) → searches verified_claims in Postgres.

WILLOW_ROOT must be set in the environment for verify() to work.
"""

import os
import sys
from typing import Optional

APP_ID = "source-trail"

_WILLOW_ROOT = os.environ.get("WILLOW_ROOT", os.path.expanduser("~/github/willow-2.0"))


def _get_source_trail():
    """Lazy import of core/source_trail.py from WILLOW_ROOT."""
    core_path = os.path.join(_WILLOW_ROOT, "core")
    if core_path not in sys.path:
        sys.path.insert(0, _WILLOW_ROOT)
    import importlib
    return importlib.import_module("core.source_trail")


def verify(text: str, document_ref: Optional[str] = None) -> dict:
    """
    Extract and verify claims in text against Jeles sources.
    Persists each result to verified_claims. Returns summary dict.

    Requires WILLOW_ROOT pointing to a willow-2.0 checkout with
    core/source_trail.py present.
    """
    try:
        st = _get_source_trail()
    except Exception as e:
        return {"ok": False, "error": f"Could not load core/source_trail: {e}",
                "claims": [], "total": 0, "matched": 0}

    try:
        result = st.verify_text(text)
    except Exception as e:
        return {"ok": False, "error": f"verify_text failed: {e}",
                "claims": [], "total": 0, "matched": 0}

    from sources_db import get_connection, release_connection, init_schema, store_verified_claim
    conn = None
    stored = 0
    try:
        conn = get_connection()
        init_schema(conn)
        for claim in result.get("claims", []):
            store_verified_claim(
                conn,
                claim_text=claim.get("claim", ""),
                matched=bool(claim.get("matched", False)),
                title=claim.get("title"),
                url=claim.get("url"),
                date=claim.get("date"),
                source=claim.get("source"),
                tier=claim.get("tier"),
                confidence=claim.get("confidence"),
                document_ref=document_ref,
            )
            stored += 1
    except Exception as e:
        return {"ok": False, "error": f"DB write failed: {e}",
                "claims": result.get("claims", []),
                "total": result.get("total", 0),
                "matched": result.get("matched", 0)}
    finally:
        if conn:
            release_connection(conn)

    return {
        "ok": True,
        "claims": result.get("claims", []),
        "total": result.get("total", 0),
        "matched": result.get("matched", 0),
        "stored": stored,
        "document_ref": document_ref,
    }


def query(q: str, document_ref: Optional[str] = None,
          matched_only: bool = False, limit: int = 50) -> list:
    """Search stored verified claims in Postgres."""
    from sources_db import get_connection, release_connection, search_verified_claims
    conn = None
    try:
        conn = get_connection()
        return search_verified_claims(
            conn, query=q, document_ref=document_ref,
            matched_only=matched_only, limit=limit,
        )
    except Exception:
        return []
    finally:
        if conn:
            release_connection(conn)


def status() -> dict:
    """Health check — confirms DB connection and WILLOW_ROOT wiring."""
    willow_root_ok = os.path.isfile(
        os.path.join(_WILLOW_ROOT, "core", "source_trail.py")
    )
    db_ok = False
    try:
        from sources_db import get_connection, release_connection
        conn = get_connection()
        release_connection(conn)
        db_ok = True
    except Exception:
        pass
    return {
        "ok": willow_root_ok and db_ok,
        "willow_root": _WILLOW_ROOT,
        "willow_root_ok": willow_root_ok,
        "db_ok": db_ok,
        "mode": "postgres",
    }
