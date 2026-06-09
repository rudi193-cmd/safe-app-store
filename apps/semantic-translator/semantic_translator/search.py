"""Semantic search over ingested translation corpus via Jeles."""
from __future__ import annotations

from . import mcp_client


def search(query: str, limit: int = 5) -> list[dict]:
    """Return segments semantically similar to query, ranked by meaning."""
    if not mcp_client.ensure_started():
        raise RuntimeError(f"MCP unavailable: {mcp_client.last_error()}")

    result = mcp_client.jeles_search(query=query, limit=limit)

    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        return result.get("results", result.get("atoms", []))
    return []


def format_result(r: dict, index: int) -> str:
    score = r.get("score", r.get("certainty", r.get("similarity", "?")))
    title = r.get("title", "")
    content = r.get("content", r.get("text", str(r)))
    lines = [f"[{index}] {title}  (score: {score})"]
    lines.append(content[:500])
    return "\n".join(lines)
