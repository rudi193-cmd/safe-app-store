"""Local Willow/Binder knowledge search for AskJeles."""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
from hashlib import sha1
from pathlib import Path
from typing import Any

log = logging.getLogger("jeles.kb")

_MAX_SOIL_DBS = 80
_MAX_SOIL_ROWS_PER_DB = 3
_STOP = {
    "about", "what", "where", "when", "which", "would", "could", "should",
    "search", "find", "tell", "show", "with", "from", "that", "this", "have",
    "your", "into", "does", "near", "need", "want",
}


def _store_root() -> Path:
    return Path(os.environ.get("WILLOW_STORE_ROOT", str(Path.home() / ".willow" / "store"))).expanduser()


def _views_dir() -> Path:
    path = Path.home() / ".willow" / "jeles_kb_views"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _tokens(query: str) -> list[str]:
    out: list[str] = []
    for token in re.findall(r"[a-z0-9][a-z0-9_-]{2,}", query.lower()):
        if token not in _STOP:
            out.append(token)
    return list(dict.fromkeys(out))


def _text(value: Any, limit: int = 500) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return re.sub(r"\s+", " ", value).strip()[:limit]
    if isinstance(value, (list, tuple)):
        return re.sub(r"\s+", " ", " ".join(_text(v, 120) for v in value)).strip()[:limit]
    if isinstance(value, dict):
        parts = []
        for key in ("summary", "content", "description", "note", "body", "text"):
            if value.get(key):
                parts.append(_text(value.get(key), 180))
        return re.sub(r"\s+", " ", " ".join(parts) or json.dumps(value, default=str)).strip()[:limit]
    return str(value).strip()[:limit]


def _title(row: dict[str, Any], fallback: str = "Knowledge note") -> str:
    for key in ("title", "name", "atom_title", "subject", "id", "_id"):
        val = row.get(key)
        if val:
            return _text(val, 120) or fallback
    return fallback


def _snippet(row: dict[str, Any]) -> str:
    for key in ("summary", "content", "description", "note", "body", "text"):
        val = row.get(key)
        if val:
            return _text(val, 420)
    return _text(row, 420)


def _write_kb_view(row: dict[str, Any], source: str, rid: str) -> str:
    """Materialize a local Markdown view so KB hits open from the TUI."""
    digest = sha1(f"{source}:{rid}".encode("utf-8", errors="ignore")).hexdigest()[:12]
    title = _title(row)
    path = _views_dir() / f"{digest}.md"
    body = [
        f"# {title}\n\n",
        f"- Source: `{source}`\n",
        f"- ID: `{rid}`\n",
    ]
    if row.get("tier"):
        body.append(f"- Tier: `{row.get('tier')}`\n")
    if row.get("status"):
        body.append(f"- Status: `{row.get('status')}`\n")
    if row.get("created_at") or row.get("updated_at"):
        body.append(f"- Date: `{row.get('updated_at') or row.get('created_at')}`\n")
    body.append("\n## Summary\n\n")
    body.append((_snippet(row) or "(no summary)") + "\n\n")
    body.append("## Full Record\n\n```json\n")
    body.append(json.dumps(row, indent=2, ensure_ascii=False, default=str))
    body.append("\n```\n")
    path.write_text("".join(body), encoding="utf-8")
    return path.as_uri()


def _kb_hit(row: dict[str, Any], source: str, idx: int) -> dict[str, Any]:
    tier = row.get("tier") or row.get("status") or row.get("confidence") or "verified"
    rid = row.get("id") or row.get("_id") or row.get("atom_id") or f"{source}:{idx}"
    url = _write_kb_view(row, source, str(rid))
    return {
        "title": _title(row),
        "url": url,
        "snippet": _snippet(row),
        "source": f"Willow KB ({source})",
        "date": row.get("updated_at") or row.get("created_at") or "",
        "source_id": "local_kb",
        "hostname": "willow.local",
        "confidence": str(tier),
        "kb_source": source,
        "kb_id": rid,
    }


def _looks_verified(row: dict[str, Any]) -> bool:
    """Keep the KB drawer for ratified/usable knowledge, not raw unverified notes."""
    title = _title(row).lower()
    snippet = _snippet(row).lower()
    status = str(row.get("status") or row.get("tier") or row.get("verdict") or "").lower()
    confidence = str(row.get("confidence") or row.get("certainty") or "").lower()

    if "[unverified]" in title or "[unverified]" in snippet:
        return False
    if status in {"unverified", "rejected", "superseded", "drifted", "failed"}:
        return False
    if confidence in {"low", "unverified"}:
        return False
    return True


def _from_mcp(query: str, limit: int) -> list[dict[str, Any]]:
    try:
        from askjeles import mcp_client

        if not mcp_client.ensure_started(timeout=8):
            return []
        payload = mcp_client.kb_search(query, limit=limit, semantic=False)
    except Exception as exc:
        log.debug("MCP kb_search unavailable: %s", exc)
        return []

    if not isinstance(payload, dict) or payload.get("error"):
        return []

    hits: list[dict[str, Any]] = []
    for source in ("knowledge", "jeles_atoms", "opus_atoms"):
        rows = payload.get(source) or []
        for row in rows:
            if isinstance(row, dict) and _looks_verified(row):
                hits.append(_kb_hit(row, source, len(hits) + 1))
                if len(hits) >= limit:
                    return hits
    return hits


def _soil_db_paths() -> list[Path]:
    root = _store_root()
    if not root.exists():
        return []
    return sorted(root.glob("**/store.db"))[:_MAX_SOIL_DBS]


def _from_soil(query: str, limit: int) -> list[dict[str, Any]]:
    terms = _tokens(query)
    if not terms:
        return []
    like = "%" + "%".join(terms[:4]) + "%"
    hits: list[dict[str, Any]] = []
    root = _store_root()

    for db_path in _soil_db_paths():
        if len(hits) >= limit:
            break
        try:
            conn = sqlite3.connect(str(db_path))
            rows = conn.execute(
                """
                SELECT id, data, updated_at
                FROM records
                WHERE deleted=0 AND lower(data) LIKE ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (like.lower(), _MAX_SOIL_ROWS_PER_DB),
            ).fetchall()
            conn.close()
        except Exception:
            continue

        collection = str(db_path.parent.relative_to(root))
        for rid, raw, updated_at in rows:
            try:
                row = json.loads(raw)
            except Exception:
                row = {"content": raw}
            row.setdefault("_id", rid)
            row.setdefault("updated_at", updated_at)
            if not _looks_verified(row):
                continue
            hit = _kb_hit(row, f"soil:{collection}", len(hits) + 1)
            haystack = f"{hit['title']} {hit['snippet']}".lower()
            if all(term in haystack for term in terms[:2]):
                hits.append(hit)
            if len(hits) >= limit:
                break
    return hits


def search_local_kb(query: str, limit: int = 8) -> list[dict[str, Any]]:
    """Search the user's own Willow KB/Binder before external sources."""
    query = (query or "").strip()
    if not query:
        return []

    hits = _from_mcp(query, limit)
    if hits:
        return hits[:limit]

    return _from_soil(query, limit)[:limit]
