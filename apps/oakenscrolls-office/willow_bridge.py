"""
willow_bridge.py — the ONE outward seam. b17: OAKOF

Deliberately OUTSIDE the no-egress zone (utety/knowledge.py pattern): the core
ledger and the math never import this module; it imports them. Everything here
is optional and degrades to a silent no-op when Willow is absent (design D4).

Two seams, both borrowed from willow-mcp:
  * surface_due()   — the dew (commitments/proactive.py): publish due
                      predictions to a signal file hooks can read. Off by
                      default; OAKENSCROLL_PROACTIVE=1 enables.
  * promote_resolved() — the gaps.py promote pattern: a resolved prediction
                      can become a knowledge atom. The ingest callable is
                      INJECTED (willow-mcp's knowledge_ingest, or anything
                      with the same shape); no willow import here, ever.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import office_db as db


def proactive_enabled() -> bool:
    return os.environ.get("OAKENSCROLL_PROACTIVE", "").strip().lower() in (
        "1", "true", "yes", "on",
    )


def signal_path() -> Path:
    home = Path(os.environ.get("WILLOW_HOME", Path.home() / ".willow"))
    return home / "signals" / "oakenscroll_dew.json"


def surface_due(now: Optional[int] = None) -> bool:
    """Publish due predictions to the signal file. Facts only: id, claim,
    confidence, due. Returns True when anything was published."""
    if not proactive_enabled():
        return False
    due = db.due_now(now)
    if not due:
        return False
    payload = {
        "published_at": datetime.now(timezone.utc).isoformat(),
        "app_id": "oakenscrolls-office",
        "due": [
            {"id": d["id"], "claim": d["claim"], "confidence": d["confidence"], "due": d["due"]}
            for d in due
        ],
    }
    path = signal_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2))
        return True
    except OSError:
        return False


def promote_resolved(pid: str, ingest: Optional[Callable[[dict], object]] = None) -> Optional[dict]:
    """Build a knowledge atom from a resolved prediction and hand it to an
    injected ingest callable. With no callable, returns the atom without
    sending it anywhere — the caller decides; this module never phones home."""
    record = db.current(pid)
    if record["status"] != "resolved":
        raise ValueError("only a resolved prediction can be promoted")
    ev = record.get("evidence") or {}
    cite, tags, source = "", ["prediction", "calibration"] + record["tags"], "oakenscrolls-office"
    if ev:
        commit = (ev.get("catalog_commit") or "")[:12]
        cite = (f" Resolved with almanac evidence: {ev.get('entry_id')} "
                f"in {ev.get('vertical')}@{commit} — {ev.get('canonical_url', '')}.")
        tags += ["almanac-cited", ev.get("vertical", "")]
        source = f"oakenscrolls-office via {ev.get('vertical', 'almanac-data')}"
    atom = {
        "id": f"oakenscroll-{record['id']}",
        "content": (
            f"Prediction graded: \"{record['claim']}\" — stated at "
            f"{record['confidence']:.0%}, outcome {'TRUE' if record['outcome'] else 'FALSE'}.{cite}"
        ),
        "domain": "calibration",
        "source": source,
        "tags": tags,
    }
    if ingest is not None:
        ingest(atom)
    return atom
