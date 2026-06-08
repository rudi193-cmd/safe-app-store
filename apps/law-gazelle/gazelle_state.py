"""
gazelle_state.py — Sidecar overlay for Law Gazelle.

Tracks resolutions, notes, and snoozes without modifying Nest SQLite files.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

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
CREATE TABLE IF NOT EXISTS activity (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type  TEXT NOT NULL,
    summary     TEXT NOT NULL,
    source_db   TEXT,
    item_type   TEXT,
    item_id     TEXT,
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fact_verification (
    source_db   TEXT NOT NULL,
    item_type   TEXT NOT NULL,
    item_id     TEXT NOT NULL,
    status      TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (source_db, item_type, item_id)
);
CREATE TABLE IF NOT EXISTS matter_stage (
    matter_key  TEXT PRIMARY KEY,
    stage       TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ai_cache (
    cache_key         TEXT PRIMARY KEY,
    event_type        TEXT NOT NULL,
    source_db         TEXT,
    item_type         TEXT,
    item_id           TEXT,
    body              TEXT NOT NULL,
    model             TEXT,
    input_fingerprint TEXT NOT NULL,
    created_at        TEXT NOT NULL,
    expires_at        TEXT
);
CREATE INDEX IF NOT EXISTS idx_user_notes_item ON user_notes (source_db, item_type, item_id);
CREATE INDEX IF NOT EXISTS idx_activity_event_time ON activity (event_type, created_at);
"""


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


_AI_CACHE_TTL_DAYS = 7


def _connect() -> sqlite3.Connection:
    APP_DATA.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(STATE_DB)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    conn.commit()
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(ai_cache)").fetchall()}
    if "expires_at" not in cols:
        conn.execute("ALTER TABLE ai_cache ADD COLUMN expires_at TEXT")
        conn.commit()


def log_activity(
    event_type: str,
    summary: str,
    *,
    source_db: str | None = None,
    item_type: str | None = None,
    item_id: str | None = None,
) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO activity (event_type, summary, source_db, item_type, item_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (event_type, summary, source_db, item_type, item_id, _now()),
        )
        conn.commit()


def fingerprint_payload(payload: Any) -> str:
    """Stable hash for cache invalidation when inputs change."""
    text = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(text.encode()).hexdigest()[:24]


def ai_cache_key(event_type: str, scope: str) -> str:
    return f"{event_type}:{scope}"


def get_ai_cache(cache_key: str, *, fingerprint: str | None = None) -> dict | None:
    """Return cached LLM output when fingerprint matches and TTL has not expired."""
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT cache_key, event_type, source_db, item_type, item_id,
                   body, model, input_fingerprint, created_at, expires_at
            FROM ai_cache WHERE cache_key=?
            """,
            (cache_key,),
        ).fetchone()
    if not row:
        return None
    data = dict(row)
    if fingerprint is not None and data.get("input_fingerprint") != fingerprint:
        return None
    expires = data.get("expires_at")
    if expires and expires < _now():
        return None
    return data


def _expires_at() -> str:
    from datetime import timedelta

    return (datetime.now(timezone.utc) + timedelta(days=_AI_CACHE_TTL_DAYS)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def put_ai_cache(
    cache_key: str,
    event_type: str,
    body: str,
    *,
    model: str | None = None,
    fingerprint: str,
    source_db: str | None = None,
    item_type: str | None = None,
    item_id: str | None = None,
) -> None:
    now = _now()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO ai_cache (
                cache_key, event_type, source_db, item_type, item_id,
                body, model, input_fingerprint, created_at, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                event_type = excluded.event_type,
                source_db = excluded.source_db,
                item_type = excluded.item_type,
                item_id = excluded.item_id,
                body = excluded.body,
                model = excluded.model,
                input_fingerprint = excluded.input_fingerprint,
                created_at = excluded.created_at,
                expires_at = excluded.expires_at
            """,
            (
                cache_key,
                event_type,
                source_db,
                item_type,
                item_id,
                body,
                model,
                fingerprint,
                now,
                _expires_at(),
            ),
        )
        conn.commit()


def clear_ai_cache(
    *,
    cache_key: str | None = None,
    event_type: str | None = None,
    source_db: str | None = None,
    item_type: str | None = None,
    item_id: str | None = None,
) -> int:
    """Drop cached LLM outputs. Returns rows deleted."""
    clauses: list[str] = []
    params: list[Any] = []
    if cache_key:
        clauses.append("cache_key=?")
        params.append(cache_key)
    if event_type:
        clauses.append("event_type=?")
        params.append(event_type)
    if source_db:
        clauses.append("source_db=?")
        params.append(source_db)
    if item_type:
        clauses.append("item_type=?")
        params.append(item_type)
    if item_id:
        clauses.append("item_id=?")
        params.append(item_id)
    if not clauses:
        return 0
    where = " AND ".join(clauses)
    with _connect() as conn:
        cur = conn.execute(f"DELETE FROM ai_cache WHERE {where}", params)
        conn.commit()
        return int(cur.rowcount)


def list_activity(limit: int = 30) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT event_type, summary, source_db, item_type, item_id, created_at
            FROM activity ORDER BY id DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def set_fact_verification(
    source_db: str,
    item_type: str,
    item_id: str,
    status: str,
) -> None:
    """status: verified | needs_source | do_not_use"""
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO fact_verification (source_db, item_type, item_id, status, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(source_db, item_type, item_id) DO UPDATE SET
                status = excluded.status,
                updated_at = excluded.updated_at
            """,
            (source_db, item_type, item_id, status, _now()),
        )
        conn.commit()
    clear_ai_cache(
        event_type="ai_fact_inspect",
        source_db=source_db,
        item_type=item_type,
        item_id=item_id,
    )
    log_activity(
        "fact_verification",
        f"Fact {item_id} marked {status}",
        source_db=source_db,
        item_type=item_type,
        item_id=item_id,
    )


def get_fact_verification(source_db: str, item_type: str, item_id: str) -> str | None:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT status FROM fact_verification
            WHERE source_db=? AND item_type=? AND item_id=?
            """,
            (source_db, item_type, item_id),
        ).fetchone()
    return row["status"] if row else None


def set_matter_stage(matter_key: str, stage: str) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO matter_stage (matter_key, stage, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(matter_key) DO UPDATE SET
                stage = excluded.stage,
                updated_at = excluded.updated_at
            """,
            (matter_key, stage, _now()),
        )
        conn.commit()
    log_activity("matter_stage", f"{matter_key} → {stage}")


def get_matter_stage(matter_key: str) -> str | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT stage FROM matter_stage WHERE matter_key=?",
            (matter_key,),
        ).fetchone()
    return row["stage"] if row else None


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
    log_activity(
        "resolved",
        f"Marked resolved: {item_type} {item_id}",
        source_db=source_db,
        item_type=item_type,
        item_id=item_id,
    )


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
    log_activity(
        "snooze",
        f"Snoozed until {until_date}: {item_type} {item_id}",
        source_db=source_db,
        item_type=item_type,
        item_id=item_id,
    )


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
    preview = body.strip()[:80]
    log_activity(
        "note",
        f"Note added: {preview}{'…' if len(body.strip()) > 80 else ''}",
        source_db=source_db,
        item_type=item_type,
        item_id=item_id,
    )


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
