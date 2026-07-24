# b17: SAPS1  ΔΣ=42
"""
willow_read.py — the ONE inward READ seam for The Binder.

This is the READ mirror of private-ledger's willow_bridge (the WRITE seam):
the app (app.py) imports THIS module; this module never imports app.py, and
never ``import willow``. Direction is always seam -> stdlib/lazy-fallback,
never seam -> app.

Rule #1 of the store (CLAUDE.md): "KB reads → knowledge_search". The preferred
path here is therefore an INJECTED willow-mcp client whose ``knowledge_search``
tool returns knowledge atoms. Only when no client is injected does the seam
fall back to the legacy direct-Postgres query — the anti-pattern this refactor
exists to demote. That fallback's psycopg2 import is LAZY (inside the fallback
function only), so importing this module, and running its tests, needs neither
textual nor psycopg2.

The seam NEVER raises out of ``search()``: every backend error degrades to an
empty list, preserving The Binder's graceful-degradation UX.
"""
from __future__ import annotations

import os
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


# ── The legacy Postgres fallback (relocated verbatim from app.py) ──────────────

def _postgres_search(query: str, limit: int = 20) -> list[dict]:
    """Direct-Postgres KB search — the legacy path, moved verbatim from
    app.py's ``_init_willow._search``. psycopg2 is imported LAZILY here so the
    seam (and its tests) load without it. NEVER raises: any error -> []."""
    try:
        import psycopg2  # lazy: absent in the mcp-preferred path and in tests

        db = os.environ.get("WILLOW_PG_DB", "willow_19")
        user = os.environ.get("WILLOW_PG_USER", os.environ.get("USER", ""))

        words = [w for w in query.lower().split() if len(w) > 2]
        if not words:
            return []
        conn = psycopg2.connect(dbname=db, user=user)
        cur = conn.cursor()
        ilike = " OR ".join(["(title ILIKE %s OR summary ILIKE %s)"] * len(words))
        params = [p for w in words for p in (f"%{w}%", f"%{w}%")]
        cur.execute(
            f"SELECT title, summary, project FROM willow.knowledge "
            f"WHERE invalid_at IS NULL AND ({ilike}) LIMIT %s",
            params + [limit],
        )
        rows = cur.fetchall()
        conn.close()
        return [{"title": r[0], "summary": r[1], "project": r[2]} for r in rows]
    except Exception:
        return []


def _psycopg2_importable() -> bool:
    """Best-effort probe for the postgres backend: is psycopg2 importable?
    Does NOT open a connection — merely importability is treated as the
    postgres signal per the seam spec."""
    try:
        import importlib.util

        return importlib.util.find_spec("psycopg2") is not None
    except Exception:
        return False


# ── The seam ──────────────────────────────────────────────────────────────────

def active_backend() -> str:
    """Which backend a search would use right now: "mcp" when a client is
    injected, else "postgres" when psycopg2 looks importable (and a WILLOW_PG_DB
    is plausible — always true, since it defaults), else "none"."""
    if _client is not None:
        return "mcp"
    if _psycopg2_importable():
        return "postgres"
    return "none"


def available() -> bool:
    """True when some backend could return results (mcp or postgres)."""
    return active_backend() != "none"


def search(query: str, limit: int = 20, *, client: Optional[KnowledgeClient] = None) -> list[dict]:
    """Search the Willow KB, returning display dicts ``{title, summary,
    project}``. NEVER raises — every backend error degrades to [].

    Preference order (rule #1):
      1. An injected client (the ``client`` arg, else the module-level one):
         call ``client.knowledge_search`` and normalize each atom.
      2. The legacy Postgres fallback.
      3. []."""
    active = client if client is not None else _client
    if active is not None:
        try:
            atoms = active.knowledge_search(query, limit)
        except Exception:
            return []
        if not atoms:
            return []
        return [_normalize(a) for a in atoms]

    if _psycopg2_importable():
        return _postgres_search(query, limit)

    return []
