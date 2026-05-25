"""
gazelle_state.py — Sidecar overlay for Law Gazelle.

Tracks resolutions, notes, and snoozes without modifying Nest SQLite files.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

APP_ID = "law-gazelle"
APP_DATA = Path(os.environ.get("APP_DATA", Path.home() / ".willow" / "apps" / APP_ID))
STATE_DB = APP_DATA / "gazelle_state.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS item_status (
    source_db   TEXT NOT NULL,
    item_type   TEXT NOT NULL,
    item_id     TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'resolved',
    notes       TEXT,
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (source_db, item_type, item_id)
);
CREATE TABLE IF NOT EXISTS snooze (
    source_db   TEXT NOT NULL,
    item_type   TEXT NOT NULL,
    item_id     TEXT NOT NULL,
    until_date  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (source_db, item_type, item_id)
);
CREATE TABLE IF NOT EXISTS user_notes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source_db   TEXT NOT NULL,
    item_type   TEXT NOT NULL,
    item_id     TEXT NOT NULL,
    body        TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _connect() -> sqlite3.Connection:
    APP_DATA.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(STATE_DB)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn


def mark_resolved(
    source_db: str,
    item_type: str,
    item_id: str,
    notes: str | None = None,
    status: str = "resolved",
) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO item_status (source_db, item_type, item_id, status, notes, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_db, item_type, item_id) DO UPDATE SET
                status = excluded.status,
                notes = excluded.notes,
                updated_at = excluded.updated_at
            """,
            (source_db, item_type, item_id, status, notes, _now()),
        )
        conn.commit()


def clear_status(source_db: str, item_type: str, item_id: str) -> None:
    with _connect() as conn:
        conn.execute(
            "DELETE FROM item_status WHERE source_db=? AND item_type=? AND item_id=?",
            (source_db, item_type, item_id),
        )
        conn.commit()


def snooze_until(
    source_db: str,
    item_type: str,
    item_id: str,
    until_date: str,
) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO snooze (source_db, item_type, item_id, until_date, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(source_db, item_type, item_id) DO UPDATE SET
                until_date = excluded.until_date,
                updated_at = excluded.updated_at
            """,
            (source_db, item_type, item_id, until_date, _now()),
        )
        conn.commit()


def add_note(
    source_db: str,
    item_type: str,
    item_id: str,
    body: str,
) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO user_notes (source_db, item_type, item_id, body, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (source_db, item_type, item_id, body.strip(), _now()),
        )
        conn.commit()


def get_status(source_db: str, item_type: str, item_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT status, notes, updated_at FROM item_status
            WHERE source_db=? AND item_type=? AND item_id=?
            """,
            (source_db, item_type, item_id),
        ).fetchone()
    return dict(row) if row else None


def get_snooze(source_db: str, item_type: str, item_id: str) -> str | None:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT until_date FROM snooze
            WHERE source_db=? AND item_type=? AND item_id=?
            """,
            (source_db, item_type, item_id),
        ).fetchone()
    return row["until_date"] if row else None


def list_notes(source_db: str, item_type: str, item_id: str) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT body, created_at FROM user_notes
            WHERE source_db=? AND item_type=? AND item_id=?
            ORDER BY id ASC
            """,
            (source_db, item_type, item_id),
        ).fetchall()
    return [dict(r) for r in rows]


def all_statuses() -> dict[tuple[str, str, str], dict]:
    """Map (source_db, item_type, item_id) -> status row."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT source_db, item_type, item_id, status, notes, updated_at FROM item_status"
        ).fetchall()
    return {(r["source_db"], r["item_type"], r["item_id"]): dict(r) for r in rows}


def all_snoozes() -> dict[tuple[str, str, str], str]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT source_db, item_type, item_id, until_date FROM snooze"
        ).fetchall()
    return {(r["source_db"], r["item_type"], r["item_id"]): r["until_date"] for r in rows}


def is_snoozed(source_db: str, item_type: str, item_id: str, today: str | None = None) -> bool:
    until = get_snooze(source_db, item_type, item_id)
    if not until:
        return False
    today = today or date.today().isoformat()
    return until > today


def effective_resolved(
    source_db: str,
    item_type: str,
    item_id: str,
    source_status: str | None = None,
) -> bool:
    overlay = get_status(source_db, item_type, item_id)
    if overlay and overlay.get("status") == "resolved":
        return True
    if source_status in ("resolved", "closed"):
        return True
    return False
