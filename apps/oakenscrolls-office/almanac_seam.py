"""
almanac_seam.py — resolution evidence from local almanac-data clones. b17: OAKOF

The almanac-data org ("catalog, don't host") publishes versioned catalogs of
pointers to authoritative public datasets — climate, economy, justice, health,
and friends. This seam lets a world-facing prediction be graded WITH A CITATION:
"resolved FALSE, per berkeley-earth-temperature in climate-almanac @ a1b2c3d".

Sovereign by construction: this module reads LOCAL CLONES only. No network,
no subprocess — it lives inside the no-egress zone (tests/test_no_egress.py).
The human syncs the catalogs with git on their own terms; the seam only ever
opens files under ALMANAC_DATA_ROOT (default ~/github/almanac-data). The
clone's git commit is read straight from .git files and pinned into the
citation, so evidence records *which version of the catalog* vouched.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Optional


def almanac_root() -> Path:
    return Path(
        os.environ.get("ALMANAC_DATA_ROOT", str(Path.home() / "github" / "almanac-data"))
    ).expanduser()


def _head_commit(repo: Path) -> Optional[str]:
    """The clone's HEAD sha via plain file reads — no git binary, no subprocess."""
    head = repo / ".git" / "HEAD"
    try:
        text = head.read_text().strip()
    except OSError:
        return None
    if not text.startswith("ref:"):
        return text or None
    ref = text.split(None, 1)[1].strip()
    loose = repo / ".git" / ref
    try:
        return loose.read_text().strip()
    except OSError:
        pass
    packed = repo / ".git" / "packed-refs"
    try:
        for line in packed.read_text().splitlines():
            if line.endswith(ref) and not line.startswith(("#", "^")):
                return line.split()[0]
    except OSError:
        pass
    return None


def verticals() -> list[dict]:
    """Local almanac clones: any direct child of the root with a catalog.json."""
    root = almanac_root()
    if not root.is_dir():
        return []
    out = []
    for child in sorted(root.iterdir()):
        catalog = child / "catalog.json"
        if child.is_dir() and catalog.is_file():
            out.append({"name": child.name, "path": child, "commit": _head_commit(child)})
    return out


def _entry_text(entry: dict) -> str:
    parts = [
        entry.get("id", ""),
        entry.get("title", ""),
        entry.get("description", ""),
        entry.get("publisher", ""),
        " ".join(entry.get("topics") or []),
    ]
    return " ".join(parts).lower()


def search(query: str, limit: int = 8) -> list[dict]:
    """Match query tokens (AND) against entry id/title/description/publisher/
    topics across every local vertical. Live sources rank above frozen/dead.
    Returns citation candidates; empty list when no clones exist."""
    tokens = [t for t in query.lower().split() if t]
    if not tokens:
        return []
    hits = []
    for v in verticals():
        try:
            catalog = json.loads((v["path"] / "catalog.json").read_text())
        except (OSError, json.JSONDecodeError):
            continue
        for entry in catalog.get("entries", []):
            text = _entry_text(entry)
            if all(t in text for t in tokens):
                source = entry.get("source") or {}
                hits.append({
                    "vertical": v["name"],
                    "entry_id": entry.get("id"),
                    "title": entry.get("title"),
                    "publisher": entry.get("publisher"),
                    "canonical_url": source.get("canonical_url"),
                    "status": entry.get("status"),
                    "license": entry.get("license"),
                    "catalog_commit": v["commit"],
                })
    hits.sort(key=lambda h: (h["status"] != "live", h["vertical"], h["entry_id"] or ""))
    return hits[:limit]


def citation(candidate: dict, note: Optional[str] = None) -> dict:
    """The evidence record a resolution carries: which source vouched, in which
    vertical, at which catalog version, observed when. Facts only."""
    return {
        "kind": "almanac-data",
        "vertical": candidate["vertical"],
        "entry_id": candidate["entry_id"],
        "title": candidate["title"],
        "publisher": candidate["publisher"],
        "canonical_url": candidate["canonical_url"],
        "catalog_commit": candidate["catalog_commit"],
        "cited_at": int(time.time()),
        "note": note,
    }
