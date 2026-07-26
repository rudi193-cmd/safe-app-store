# b17: SAPS1  ΔΣ=42
"""
willow_read.py — the ONE inward READ seam for The Binder.

This is the READ mirror of private-ledger's willow_bridge (the WRITE seam):
the app (app.py) imports THIS module; this module never imports app.py, and
never ``import willow``. Direction is always seam -> stdlib/lazy-fallback,
never seam -> app.

Rule #1 of the store (CLAUDE.md): "KB reads → knowledge_search". The KB is read
ONLY through an INJECTED willow-mcp client whose ``knowledge_search`` tool scopes
results to this app server-side. The old direct-Postgres fallback read
``willow.knowledge`` with NO app scope (it returned any app's rows matching the
words) — a gate-bypass of the same class as box audit B3, missed in the first
pass because it queried ``willow.knowledge`` rather than ``records``. It is
removed: with no gated client injected there is no safe read, so ``search``
returns []. (Same discipline as the shared ``willow_read`` library, box audit A5;
The Binder keeps its own copy only because its module name collides with the
package name, and it adds the app-specific atom→display normalization below.)

The seam NEVER raises out of ``search()``: every backend error degrades to an
empty list, preserving The Binder's graceful-degradation UX.
"""
from __future__ import annotations

from typing import Any, Optional, Protocol, runtime_checkable


# ── The client contract (willow-mcp tool shape) ───────────────────────────────

@runtime_checkable
class KnowledgeClient(Protocol):
    """Structural type for anything that can search the Willow KB.

    Mirrors the willow-mcp ``knowledge_search`` tool: given a query and a
    limit, return a list of knowledge atoms. An atom is a dict shaped roughly
    like ``{content, domain, source, tags, title?, project?}`` — the seam is
    tolerant of missing keys when normalizing.
    """

    def knowledge_search(self, query: str, limit: int) -> list[dict]:
        ...


# ── Module-level injectable client ────────────────────────────────────────────

_client: Optional[KnowledgeClient] = None


def set_client(client: Optional[KnowledgeClient]) -> None:
    """Inject (or clear, with None) the preferred knowledge_search client."""
    global _client
    _client = client


def get_client() -> Optional[KnowledgeClient]:
    """Return the currently-injected client, or None."""
    return _client


# ── Normalization: KB atom -> display dict ────────────────────────────────────

def _normalize(atom: Any) -> dict:
    """Map a willow-mcp knowledge atom to the display shape app.py renders:
    ``{"title", "summary", "project"}``. Tolerant of missing keys and of
    non-dict rows (which normalize to empty strings)."""
    if not isinstance(atom, dict):
        return {"title": "", "summary": "", "project": ""}

    title = atom.get("title")
    if not title:
        # Atoms often carry no explicit title; source is the next-best label.
        title = atom.get("source") or ""

    # willow-mcp atoms carry the body under "content"; the display column is
    # "summary". Accept either, preferring an explicit summary if present.
    summary = atom.get("summary")
    if summary is None:
        summary = atom.get("content")
    if summary is None:
        summary = ""

    project = atom.get("project")
    if project is None:
        # "domain" is the willow-mcp field closest to the legacy "project".
        project = atom.get("domain")
    if project is None:
        project = ""

    return {
        "title": str(title),
        "summary": str(summary),
        "project": str(project),
    }


# ── The seam ──────────────────────────────────────────────────────────────────

def active_backend() -> str:
    """"mcp" when a gated client is injected, else "none". There is no postgres
    backend — the unscoped ``willow.knowledge`` read was removed (box audit B3)."""
    return "mcp" if _client is not None else "none"


def available() -> bool:
    """True when the gated client is injected — the only KB-read path now."""
    return active_backend() != "none"


def search(query: str, limit: int = 20, *, client: Optional[KnowledgeClient] = None) -> list[dict]:
    """Search the Willow KB through the injected gated client, returning display
    dicts ``{title, summary, project}``. NEVER raises — every backend error
    degrades to []. No client injected -> [] (the raw ``willow.knowledge``
    fallback that bypassed the gate was removed, box audit B3)."""
    active = client if client is not None else _client
    if active is None:
        return []
    try:
        atoms = active.knowledge_search(query, limit)
    except Exception:
        return []
    return [_normalize(a) for a in (atoms or [])]
