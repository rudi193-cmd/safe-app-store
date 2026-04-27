"""
timeline_db.py — SQLite backend for story-timeline v2.

Open node graph: any entity type, user-defined fields.
DB_PATH is overridable via STORY_TIMELINE_DB env var for testing.
"""
import json
import os
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

DB_PATH = Path(
    os.environ.get("STORY_TIMELINE_DB",
    str(Path.home() / ".willow" / "store" / "story-timeline" / "timeline.db"))
)


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS nodes (
            id       TEXT PRIMARY KEY,
            type     TEXT NOT NULL,
            fields   TEXT NOT NULL DEFAULT '{}',
            created  TEXT DEFAULT (datetime('now')),
            updated  TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    return conn


def add_node(type_: str, fields: dict) -> str:
    node_id = str(uuid.uuid4())
    conn = _conn()
    conn.execute(
        "INSERT INTO nodes (id, type, fields) VALUES (?, ?, ?)",
        (node_id, type_, json.dumps(fields))
    )
    conn.commit()
    conn.close()
    return node_id


def get_node(node_id: str) -> Optional[dict]:
    conn = _conn()
    row = conn.execute("SELECT * FROM nodes WHERE id = ?", (node_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_nodes(type_: Optional[str] = None) -> list[dict]:
    conn = _conn()
    if type_:
        rows = conn.execute(
            "SELECT * FROM nodes WHERE type = ? ORDER BY created ASC", (type_,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM nodes ORDER BY created ASC"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_node(node_id: str, fields: dict) -> bool:
    now = datetime.now().isoformat()
    conn = _conn()
    cur = conn.execute(
        "UPDATE nodes SET fields = ?, updated = ? WHERE id = ?",
        (json.dumps(fields), now, node_id)
    )
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def delete_node(node_id: str) -> bool:
    conn = _conn()
    cur = conn.execute("DELETE FROM nodes WHERE id = ?", (node_id,))
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def search_nodes(query: str) -> list[dict]:
    conn = _conn()
    rows = conn.execute(
        "SELECT * FROM nodes WHERE lower(fields) LIKE lower(?) OR lower(type) LIKE lower(?)",
        (f"%{query}%", f"%{query}%")
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_types() -> list[str]:
    conn = _conn()
    rows = conn.execute(
        "SELECT DISTINCT type FROM nodes ORDER BY type"
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_all_node_ids() -> list[str]:
    conn = _conn()
    rows = conn.execute("SELECT id FROM nodes").fetchall()
    conn.close()
    return [r[0] for r in rows]
