"""
nightstand_db.py — data layer for The Nightstand. b17: NSTND

The rules live here, not in the UI:
  * At most one thing is ever in your hands.
  * Things are archived, never deleted.
  * "Hand me one" offers the lightest, oldest thing first — small wins build up.
"""
from __future__ import annotations

import sqlite3
import time
from typing import Optional

from nightstand_paths import db_path

DB_PATH = db_path()

WEIGHTS = ("light", "medium", "heavy")

# Statuses: down (on the nightstand) · in_hand (the one you carry now)
#           done · archived
_WEIGHT_ORDER = "CASE weight WHEN 'light' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END"


def _db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS things (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            what       TEXT    NOT NULL,
            weight     TEXT    NOT NULL DEFAULT 'medium',
            status     TEXT    NOT NULL DEFAULT 'down',
            bite       TEXT,
            set_down   INTEGER NOT NULL,
            updated    INTEGER NOT NULL,
            pickups    INTEGER NOT NULL DEFAULT 0
        )
    """)
    conn.commit()
    return conn


def set_down(what: str, weight: str = "medium") -> int:
    """Put a new thing on the nightstand."""
    if weight not in WEIGHTS:
        weight = "medium"
    now = int(time.time())
    with _db() as c:
        cur = c.execute(
            "INSERT INTO things (what, weight, set_down, updated) VALUES (?,?,?,?)",
            (what.strip(), weight, now, now),
        )
        return cur.lastrowid


def list_things(status: str = "down") -> list[dict]:
    with _db() as c:
        return [dict(r) for r in c.execute(
            f"SELECT * FROM things WHERE status=? ORDER BY {_WEIGHT_ORDER} DESC, set_down ASC",
            (status,),
        )]


def in_hand() -> Optional[dict]:
    with _db() as c:
        row = c.execute("SELECT * FROM things WHERE status='in_hand'").fetchone()
        return dict(row) if row else None


def pick_up(thing_id: int, bite: Optional[str] = None) -> Optional[dict]:
    """Take one thing in hand. Whatever you were holding goes back down."""
    now = int(time.time())
    with _db() as c:
        c.execute(
            "UPDATE things SET status='down', updated=? WHERE status='in_hand'", (now,)
        )
        c.execute(
            "UPDATE things SET status='in_hand', bite=?, pickups=pickups+1, updated=? "
            "WHERE id=? AND status='down'",
            (bite.strip() if bite else None, now, thing_id),
        )
        row = c.execute("SELECT * FROM things WHERE id=? AND status='in_hand'", (thing_id,)).fetchone()
        return dict(row) if row else None


def hand_me_one() -> Optional[dict]:
    """The nightstand's suggestion: the lightest, oldest thing waiting."""
    with _db() as c:
        row = c.execute(
            f"SELECT * FROM things WHERE status='down' ORDER BY {_WEIGHT_ORDER} ASC, set_down ASC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None


def set_back(thing_id: int) -> None:
    """Put the thing in hand back on the nightstand. Progress is kept."""
    now = int(time.time())
    with _db() as c:
        c.execute("UPDATE things SET status='down', updated=? WHERE id=?", (now, thing_id))


def mark_done(thing_id: int) -> None:
    now = int(time.time())
    with _db() as c:
        c.execute("UPDATE things SET status='done', updated=? WHERE id=?", (now, thing_id))


def archive(thing_id: int) -> None:
    """Archive, don't delete — store rule."""
    now = int(time.time())
    with _db() as c:
        c.execute("UPDATE things SET status='archived', updated=? WHERE id=?", (now, thing_id))


def counts() -> dict:
    with _db() as c:
        rows = c.execute("SELECT status, COUNT(*) AS n FROM things GROUP BY status").fetchall()
        out = {r["status"]: r["n"] for r in rows}
        heavy = c.execute(
            "SELECT COUNT(*) AS n FROM things WHERE status='down' AND weight='heavy'"
        ).fetchone()
        out["heavy_down"] = heavy["n"]
        return out
