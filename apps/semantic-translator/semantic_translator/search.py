"""Semantic search over ingested corpus via Jeles, with local keyword fallback."""
from __future__ import annotations

import json
import pathlib
import re

from . import mcp_client

_CORPUS = pathlib.Path("data/corpus.jsonl")


def _keyword_fallback(query: str, limit: int) -> list[dict]:
    """Simple word-overlap search against corpus.jsonl when Jeles is unavailable."""
    if not _CORPUS.exists():
        return []
    words = set(re.findall(r"\w+", query.lower()))
    if not words:
        return []
    scored: list[tuple[float, dict]] = []
    with open(_CORPUS, encoding="utf-8") as f:
        for line in f:
            seg = json.loads(line)
            text_words = set(re.findall(r"\w+", seg["text"].lower()))
            overlap = len(words & text_words) / max(len(words), 1)
            if overlap > 0:
                scored.append((overlap, {
                    "title": f"{seg['lesson']} | {seg['lang']}",
                    "content": seg["text"],
                    "score": round(overlap, 3),
                    "source": "keyword",
                    "id": seg["id"],
                }))
    scored.sort(key=lambda x: -x[0])
    return [r for _, r in scored[:limit]]


def search(query: str, limit: int = 5) -> list[dict]:
    """Semantic search via Jeles; falls back to local keyword search on failure."""
    if not mcp_client.ensure_started():
        return _keyword_fallback(query, limit)

    try:
        result = mcp_client.jeles_search(query=query, limit=limit)
        atoms: list[dict] = []
        if isinstance(result, list):
            atoms = result
        elif isinstance(result, dict):
            atoms = result.get("results", result.get("atoms", []))
        if atoms:
            return atoms
        # Jeles returned empty — fall back
        return _keyword_fallback(query, limit)
    except RuntimeError as exc:
        msg = str(exc).lower()
        if "embedder" in msg or "keyword search only" in msg or "unavailable" in msg:
            return _keyword_fallback(query, limit)
        raise


def format_result(r: dict, index: int) -> str:
    score = r.get("score", r.get("certainty", r.get("similarity", "?")))
    title = r.get("title", "")
    content = r.get("content", r.get("text", str(r)))
    source = r.get("source", "")
    source_tag = f"  [{source}]" if source == "keyword" else ""
    lines = [f"[{index}] {title}  (score: {score}){source_tag}"]
    lines.append(content[:500])
    return "\n".join(lines)
