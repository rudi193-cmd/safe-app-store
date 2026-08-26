"""One gap spine — write once, read from both sides.

The handoff called out that ``jeles.corpus.log_gap(question)`` and
``willow_mcp.gaps.log(topic, question)`` are two different APIs. This
module writes to both and preserves each side's id so the promote
path can resolve the willow row it actually created.
"""
from __future__ import annotations

from typing import Any


def log_gap(question: str, *, topic: str = "fleet_glue") -> dict[str, Any]:
    """Dual-write to jeles and willow. Returns both ids and both raw responses."""
    report: dict[str, Any] = {
        "question": question,
        "topic": topic,
        "jeles": None,
        "willow": None,
        "willow_gap_id": None,
        "jeles_gap_id": None,
    }

    try:
        from jeles import corpus as jc
        fn = getattr(jc, "log_gap", None)
        if fn is None:
            report["jeles"] = {"ok": False, "detail": "jeles.corpus has no log_gap"}
        else:
            r = fn(question)
            report["jeles"] = r
            if isinstance(r, dict):
                report["jeles_gap_id"] = r.get("id") or r.get("gap_id")
    except Exception as exc:
        report["jeles"] = {"error": type(exc).__name__, "detail": str(exc)}

    try:
        from willow_mcp import gaps as wgaps
        r = wgaps.log(topic, question)
        report["willow"] = r
        if isinstance(r, dict):
            report["willow_gap_id"] = r.get("id")
    except Exception as exc:
        report["willow"] = {"error": type(exc).__name__, "detail": str(exc)}

    return report


def list_all_gaps(*, topic: str | None = None, limit: int = 20) -> dict[str, Any]:
    """Read gaps from both sides. Never raises — errors surface per side."""
    out: dict[str, Any] = {"jeles": [], "willow": []}

    try:
        from jeles import corpus as jc
        if hasattr(jc, "list_gaps"):
            out["jeles"] = list(jc.list_gaps(limit=limit) or [])[:limit]
    except Exception as exc:
        out["jeles"] = [{"error": type(exc).__name__, "detail": str(exc)}]

    try:
        from willow_mcp import gaps as wgaps
        raw = wgaps.list_gaps(topic=topic, limit=limit)
        items = raw.get("items") if isinstance(raw, dict) else raw
        out["willow"] = list(items or [])[:limit]
    except Exception as exc:
        out["willow"] = [{"error": type(exc).__name__, "detail": str(exc)}]

    return out
