"""
fleet_presence — the shared "one memory" seam. b17: FLEETP

The store's apps are silently duplicated, not connected: personas.py drifted
into 10 versions across 11 copies, safe_integration.py into 17-of-17. They
carry copies of each other instead of sharing anything live.

This is the missing shared axis — one small primitive, extracted once (the
libs/subject-consent pattern), so an app can *announce itself into the one
memory* and *see the rest of the fleet*, instead of sitting in its own SQLite
silo. It is the code behind the "one desk, one memory, many tools" thesis:
apps never wire to each other, they read/write shared atoms.

Discipline (inherited from willow's commitment membrane):
  * Standalone-safe (store decision #3): stdlib only, no willow_mcp import, no
    network. If no shared store is reachable, every call is a silent no-op —
    an app that ships this still runs with zero backend.
  * Receipts, not recording: a presence atom carries only FACTS an app chooses
    to publish (app_id, one-line summary, small counts) — never record bodies.
  * States, not deletions: withdraw() soft-deletes; the row is kept.
  * Writes willow's own `records` schema into the `fleet` collection, so the
    live willow store tools (store_search/store_get) read the very same atoms.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

COLLECTION = "fleet"

# willow's records schema, verbatim — so willow-mcp's store tools read our atoms.
_SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
    id         TEXT PRIMARY KEY,
    data       TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deviation  REAL NOT NULL DEFAULT 0.0,
    action     TEXT NOT NULL DEFAULT 'work_quiet',
    deleted    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_deleted ON records(deleted);
"""

# Facts only. A presence atom may never carry a record body — the same guard
# the commitment membrane runs, standing at this door.
_FORBIDDEN = {"body", "notes", "note", "description", "raw", "content", "records"}


def _root(explicit: Optional[str] = None) -> Optional[Path]:
    """The shared vault store, or None when there is no one-memory to join.

    Resolves WILLOW_STORE_ROOT (what every store app already uses). Returns
    None — never a home-dir guess — when it is unset AND ~/.willow/store does
    not already exist, so a truly standalone app stays silent instead of
    minting a lonely store nobody else reads."""
    if explicit:
        return Path(explicit).expanduser()
    env = os.environ.get("WILLOW_STORE_ROOT")
    if env:
        return Path(env).expanduser()
    default = Path.home() / ".willow" / "store"
    return default if default.exists() else None


def _connect(root: Path) -> sqlite3.Connection:
    db = root / COLLECTION / "store.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(db))
    c.executescript(_SCHEMA)
    return c


def _db_exists(root: Optional[Path]) -> bool:
    return root is not None and (root / COLLECTION / "store.db").exists()


def announce(
    app_id: str,
    summary: str,
    counts: Optional[dict] = None,
    *,
    store_root: Optional[str] = None,
) -> bool:
    """Publish (or refresh) this app's presence in the one memory. Keyed by
    app_id, so re-announcing updates in place. Returns True if published,
    False if there is no shared store to join (the standalone no-op)."""
    root = _root(store_root)
    if root is None:
        return False
    atom = {
        "app_id": app_id,
        "summary": str(summary)[:280],
        "counts": {str(k): int(v) for k, v in (counts or {}).items()},
        "kind": "presence",
    }
    leaked = _FORBIDDEN & set(atom["counts"])
    if leaked:
        raise ValueError(f"presence atom would leak content via {sorted(leaked)}")
    now = datetime.now(timezone.utc).isoformat()
    try:
        c = _connect(root)
        with c:
            # Keep the original created_at on refresh; only updated_at moves.
            c.execute(
                "INSERT OR REPLACE INTO records "
                "(id, data, created_at, updated_at, deviation, action, deleted) "
                "VALUES (?, ?, COALESCE((SELECT created_at FROM records WHERE id=?), ?), ?, 0.0, 'work_quiet', 0)",
                (app_id, json.dumps(atom), app_id, now, now),
            )
        c.close()
        return True
    except (OSError, sqlite3.Error):
        return False  # unwritable store → stay a no-op, never crash the app


def roster(*, store_root: Optional[str] = None) -> list[dict]:
    """Every app currently present in the one memory, oldest first. Empty when
    there is no shared store. This is how an app sees the rest of the fleet
    without importing any of them."""
    root = _root(store_root)
    if not _db_exists(root):
        return []
    try:
        c = _connect(root)
        rows = c.execute(
            "SELECT id, data, updated_at FROM records WHERE deleted=0 ORDER BY created_at"
        ).fetchall()
        c.close()
    except sqlite3.Error:
        return []
    out = []
    for rid, data, updated in rows:
        try:
            atom = json.loads(data)
        except json.JSONDecodeError:
            continue
        atom["_id"] = rid
        atom["_updated"] = updated
        out.append(atom)
    return out


def withdraw(app_id: str, *, store_root: Optional[str] = None) -> bool:
    """Leave the one memory. States-not-deletions: the row is kept (deleted=1),
    so the record that this app was once present survives."""
    root = _root(store_root)
    if not _db_exists(root):
        return False
    now = datetime.now(timezone.utc).isoformat()
    try:
        c = _connect(root)
        with c:
            c.execute("UPDATE records SET deleted=1, updated_at=? WHERE id=?", (now, app_id))
        c.close()
        return True
    except sqlite3.Error:
        return False
