"""willow_read — the one sanctioned KB-read seam for hosted apps.

Rule #1 of the store (CLAUDE.md): "KB reads -> knowledge_search". The KB is read
ONLY through an INJECTED willow-mcp client whose ``knowledge_search`` tool scopes
results to the calling app server-side. A direct read of Willow's shared SOIL
``store.db`` returned EVERY app's atoms — the records table has no per-app scope
column, so it can't be scoped — which is box-audit gate-bypass B3. There is no
raw fallback here: with no client injected there is no safe read, so ``search``
returns [].

This is the canonical version of the seam that public-ledger / the-binder /
private-ledger each hand-rolled (box audit A5). Apps depend on THIS instead of
carrying their own copy, so the gated-read discipline can't drift app to app.
Stdlib-only, egress-free, never raises out of ``search``.
"""
from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

__all__ = [
    "KnowledgeClient", "set_client", "get_client",
    "active_backend", "available", "search",
]


@runtime_checkable
class KnowledgeClient(Protocol):
    """Anything that can search the Willow KB, mirroring willow-mcp's
    ``knowledge_search`` tool: (query, limit) -> list of knowledge atoms."""

    def knowledge_search(self, query: str, limit: int) -> list[dict]:
        ...


_client: Optional[KnowledgeClient] = None


def set_client(client: Optional[KnowledgeClient]) -> None:
    """Inject (or clear, with None) the gated knowledge_search client."""
    global _client
    _client = client


def get_client() -> Optional[KnowledgeClient]:
    return _client


def active_backend() -> str:
    """"mcp" when a gated client is injected, else "none". There is no
    raw-SQLite backend — the direct store read was removed (box audit B3)."""
    return "mcp" if _client is not None else "none"


def available() -> bool:
    """True when the gated client is injected — the only KB-read path."""
    return active_backend() != "none"


def search(query: str, limit: int = 5, *,
           client: Optional[KnowledgeClient] = None) -> list[dict]:
    """Search the Willow KB, returning knowledge atoms (list of dicts). NEVER
    raises — every backend error degrades to []. An injected client (the
    ``client`` arg, else the module-level one) is the only path; with none, []."""
    active = client if client is not None else _client
    if active is None:
        return []
    try:
        atoms = active.knowledge_search(query, limit)
    except Exception:
        return []
    return [a for a in (atoms or []) if isinstance(a, dict)]
