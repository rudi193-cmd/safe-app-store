# b17: SAPS1  ΔΣ=42
"""
willow_read.py — the sanctioned KB-read seam for Public Ledger.

The READ mirror of private-ledger's willow_bridge, and a sibling of
the-binder's willow_read. app code imports THIS module; this module never
``import willow`` and never reaches into another service's database from the
caller's code.

Rule #1 of the store (CLAUDE.md): "KB reads → knowledge_search". The preferred
path is therefore an INJECTED willow-mcp client whose ``knowledge_search`` tool
returns knowledge atoms. Only when no client is injected does the seam fall back
to a direct read of Willow's local SOIL store (``store.db``) — the anti-pattern
this seam exists to demote (the old ``safe_integration.query`` did exactly that,
inline; it is now retired to ``_archived/``). That fallback isolates the direct
read here, behind the seam, so it is never sprayed through app code again.

The seam NEVER raises out of ``search()``: every backend error degrades to an
empty list.

Note: public-ledger's data comes from external public-record APIs
(USASpending / ProPublica); it has no live KB-read consumer yet. This seam is
the sanctioned path for when one lands — e.g. the cross-app entity-graph (#15)
or shared provenance (#16) work — so KB reads never regress to a direct DB hit.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional, Protocol, runtime_checkable


# ── The client contract (willow-mcp tool shape) ───────────────────────────────

@runtime_checkable
class KnowledgeClient(Protocol):
    """Anything that can search the Willow KB, mirroring willow-mcp's
    ``knowledge_search`` tool: (query, limit) -> list of knowledge atoms."""

    def knowledge_search(self, query: str, limit: int) -> list[dict]:
        ...


# ── Module-level injectable client ────────────────────────────────────────────

_client: Optional[KnowledgeClient] = None


def set_client(client: Optional[KnowledgeClient]) -> None:
    """Inject (or clear, with None) the preferred knowledge_search client."""
    global _client
    _client = client


def get_client() -> Optional[KnowledgeClient]:
    return _client


# ── The legacy SOIL-SQLite fallback (relocated from safe_integration.query) ────

def _store_root() -> str:
    return os.environ.get(
        "WILLOW_STORE_ROOT",
        os.path.join(os.path.expanduser("~"), ".willow", "store"),
    )


def _store_db_path() -> Path:
    return Path(_store_root()) / "knowledge" / "store.db"


def _sqlite_search(query: str, limit: int = 5) -> list[dict]:
    """Direct read of Willow's SOIL SQLite store — the legacy path, moved
    verbatim from the retired ``safe_integration.query``. sqlite3 is stdlib, but
    the read is isolated here and NEVER raises: any error -> []."""
    db_path = _store_db_path()
    if not db_path.exists():
        return []
    try:
        import sqlite3

        conn = sqlite3.connect(str(db_path))
        rows = conn.execute(
            "SELECT data FROM records WHERE deleted=0 AND data LIKE ? LIMIT ?",
            (f"%{query}%", limit),
        ).fetchall()
        conn.close()
        out: list[dict] = []
        for r in rows:
            try:
                out.append(json.loads(r[0]))
            except (ValueError, TypeError):
                continue
        return out
    except Exception:
        return []


# ── The seam ──────────────────────────────────────────────────────────────────

def active_backend() -> str:
    """Which backend a search would use right now: "mcp" when a client is
    injected, else "sqlite" when Willow's local store.db exists, else "none"."""
    if _client is not None:
        return "mcp"
    if _store_db_path().exists():
        return "sqlite"
    return "none"


def available() -> bool:
    """True when some backend could return results (mcp or sqlite)."""
    return active_backend() != "none"


def search(query: str, limit: int = 5, *, client: Optional[KnowledgeClient] = None) -> list[dict]:
    """Search the Willow KB, returning knowledge atoms (list of dicts). NEVER
    raises — every backend error degrades to [].

    Preference order (rule #1):
      1. An injected client (the ``client`` arg, else the module-level one):
         call ``client.knowledge_search`` and return its atoms.
      2. The legacy direct-SQLite read of Willow's local store.db.
      3. []."""
    active = client if client is not None else _client
    if active is not None:
        try:
            atoms = active.knowledge_search(query, limit)
        except Exception:
            return []
        return [a for a in (atoms or []) if isinstance(a, dict)]

    return _sqlite_search(query, limit)
