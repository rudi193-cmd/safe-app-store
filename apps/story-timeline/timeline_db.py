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


def _init_db() -> None:
    """Initialize the database schema at module import time."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
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
    conn.close()


# Initialize database schema at module import time
_init_db()


def _conn() -> sqlite3.Connection:
    """Create and return a new database connection."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def add_node(type_: str, fields: dict) -> str:
    node_id = str(uuid.uuid4())
    conn = _conn()
    try:
        conn.execute(
            "INSERT INTO nodes (id, type, fields) VALUES (?, ?, ?)",
            (node_id, type_, json.dumps(fields))
        )
        conn.commit()
        return node_id
    finally:
        conn.close()


def add_node_with_id(node_id: str, type_: str, fields: dict) -> str:
    conn = _conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO nodes (id, type, fields) VALUES (?, ?, ?)",
            (node_id, type_, json.dumps(fields))
        )
        conn.commit()
        return node_id
    finally:
        conn.close()


def get_node(node_id: str) -> Optional[dict]:
    conn = _conn()
    try:
        row = conn.execute("SELECT * FROM nodes WHERE id = ?", (node_id,)).fetchone()
        if not row:
            return None
        node = dict(row)
        node["fields"] = json.loads(node["fields"])
        return node
    finally:
        conn.close()


def get_nodes(type_: Optional[str] = None) -> list[dict]:
    conn = _conn()
    try:
        if type_:
            rows = conn.execute(
                "SELECT * FROM nodes WHERE type = ? ORDER BY created ASC", (type_,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM nodes ORDER BY created ASC"
            ).fetchall()
        nodes = [dict(r) for r in rows]
        for node in nodes:
            node["fields"] = json.loads(node["fields"])
        return nodes
    finally:
        conn.close()


def update_node(node_id: str, fields: dict) -> bool:
    now = datetime.now().isoformat()
    conn = _conn()
    try:
        cur = conn.execute(
            "UPDATE nodes SET fields = ?, updated = ? WHERE id = ?",
            (json.dumps(fields), now, node_id)
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def delete_node(node_id: str) -> bool:
    conn = _conn()
    try:
        cur = conn.execute("DELETE FROM nodes WHERE id = ?", (node_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def search_nodes(query: str) -> list[dict]:
    conn = _conn()
    try:
        # Searches the serialized JSON string — key names and values are both matched
        rows = conn.execute(
            "SELECT * FROM nodes WHERE lower(fields) LIKE lower(?) OR lower(type) LIKE lower(?)",
            (f"%{query}%", f"%{query}%")
        ).fetchall()
        nodes = [dict(r) for r in rows]
        for node in nodes:
            node["fields"] = json.loads(node["fields"])
        return nodes
    finally:
        conn.close()


def get_types() -> list[str]:
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT DISTINCT type FROM nodes ORDER BY type"
        ).fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()


def get_all_node_ids() -> list[str]:
    conn = _conn()
    try:
        rows = conn.execute("SELECT id FROM nodes").fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()
