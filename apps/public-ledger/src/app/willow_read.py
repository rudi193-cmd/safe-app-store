# b17: SAPS1  ΔΣ=42
"""
willow_read.py — the sanctioned KB-read seam for Public Ledger.

The READ mirror of private-ledger's willow_bridge, and a sibling of
the-binder's willow_read. app code imports THIS module; this module never
``import willow`` and never reaches into another service's database from the
caller's code.

Rule #1 of the store (CLAUDE.md): "KB reads → knowledge_search". The KB is read
ONLY through an INJECTED willow-mcp client whose ``knowledge_search`` tool scopes
results to this app server-side. The direct read of Willow's shared SOIL store
(``store.db``) returned EVERY app's atoms — the records table has no per-app
scope column, so it could not be scoped — which is box-audit gate-bypass B3. That
fallback is now removed here as well as from the app-inline copies (the old
``safe_integration.query`` was retired to ``_archived/`` earlier). With no client
injected there is no safe read, so ``search`` returns [].

The seam NEVER raises out of ``search()``: every backend error degrades to an
empty list.

Note: public-ledger's data comes from external public-record APIs
(USASpending / ProPublica); it has no live KB-read consumer yet. This seam is
the sanctioned path for when one lands — e.g. the cross-app entity-graph (#15)
or shared provenance (#16) work — so KB reads never regress to a direct DB hit.
"""
from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable


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


# ── The seam ──────────────────────────────────────────────────────────────────

def active_backend() -> str:
    """Which backend a search would use right now: "mcp" when a gated client is
    injected, else "none". The raw-SQLite fallback was removed (box audit B3)."""
    return "mcp" if _client is not None else "none"


def available() -> bool:
    """True when the gated client is injected — the only KB-read path now."""
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

    return []
