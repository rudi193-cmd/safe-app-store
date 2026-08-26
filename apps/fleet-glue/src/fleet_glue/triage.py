"""Operator triage summary — Seal / Known / Gaps.

Reads the Nestor SQLite store directly (columns from the shipped
``sqlite_store``: ``tm_pairs`` with ``status`` and ``origin``, plus the
per-side gap backlogs). Text summary only — a real UI is out of scope
for the lab glue.
"""
from __future__ import annotations

import os
import sqlite3
from typing import Any


def _tm_rows(db_path: str) -> list[dict[str, Any]]:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            "SELECT id, source_text, target_text, source_lang, target_lang, "
            "status, origin, verifier, reason "
            "FROM tm_pairs "
            "WHERE (superseded_by = '' OR superseded_by IS NULL) "
            "ORDER BY created_at DESC"
        ).fetchall()
    finally:
        con.close()
    return [dict(r) for r in rows]


def summary(
    db_path: str | None = None,
    *,
    include_gaps: bool = True,
) -> dict[str, Any]:
    """Group current pairs into Seal / Known / Rejected, plus both gap backlogs."""
    db = db_path or os.environ.get("NESTOR_DB")
    lanes: dict[str, list[dict[str, Any]]] = {"seal": [], "known": [], "reject": [], "other": []}

    if db and os.path.exists(db):
        for row in _tm_rows(db):
            status = (row.get("status") or "").lower()
            origin = (row.get("origin") or "").lower()
            if status == "sealed":
                lane = "seal"
            elif origin.startswith("established-") or origin.startswith("corroborated"):
                lane = "known"
            elif status == "rejected":
                lane = "reject"
            else:
                lane = "other"
            lanes[lane].append(row)

    out: dict[str, Any] = {
        "db": db,
        "counts": {k: len(v) for k, v in lanes.items()},
        "lanes": lanes,
    }

    if include_gaps:
        try:
            from .gaps_compat import list_all_gaps
            g = list_all_gaps()
            out["gaps"] = {
                "willow_open": [x for x in g.get("willow", []) if (x.get("status") or "open") == "open"],
                "jeles": g.get("jeles", []),
            }
            out["counts"]["gaps_willow_open"] = len(out["gaps"]["willow_open"])
            out["counts"]["gaps_jeles"] = len(out["gaps"]["jeles"])
        except Exception as exc:
            out["gaps"] = {"error": f"{type(exc).__name__}: {exc}"}

    return out


def render(summary_dict: dict[str, Any]) -> str:
    """Compact text render of :func:`summary` for the terminal."""
    lines: list[str] = []
    c = summary_dict.get("counts", {})
    lines.append(
        f"Seal: {c.get('seal',0):3}   "
        f"Known: {c.get('known',0):3}   "
        f"Reject: {c.get('reject',0):3}   "
        f"Other: {c.get('other',0):3}   "
        f"Gaps(willow): {c.get('gaps_willow_open',0):3}   "
        f"Gaps(jeles): {c.get('gaps_jeles',0):3}"
    )
    for lane in ("seal", "known", "reject", "other"):
        rows = summary_dict.get("lanes", {}).get(lane, [])
        if not rows:
            continue
        lines.append(f"\n  [{lane.upper()}]")
        for r in rows[:8]:
            src = (r.get("source_text") or "")[:22]
            tgt = (r.get("target_text") or "")[:40]
            lines.append(
                f"    {src:22} → {tgt:40}   "
                f"origin={r.get('origin','')[:24]:24}  verifier={r.get('verifier','') or '-'}"
            )
        if len(rows) > 8:
            lines.append(f"    …and {len(rows) - 8} more")
    return "\n".join(lines)
