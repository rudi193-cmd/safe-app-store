"""
migrate.py — Migrate v1 story-timeline events → v2 open nodes.

Detects old schema by presence of 'events' table without 'nodes' table.
Converts each event to a node of type 'event' with all fields preserved in JSON.
Idempotent: checks for migrated- prefixed node IDs before inserting.
"""
import json
import os
import sqlite3
from pathlib import Path


def _get_db_path():
    """Resolve DB path from env or default. Called at runtime to support test monkeypatching."""
    return Path(
        os.environ.get("STORY_TIMELINE_DB",
        str(Path.home() / ".willow" / "store" / "story-timeline" / "timeline.db"))
    )


def needs_migration() -> bool:
    db_path = _get_db_path()
    if not db_path.exists():
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        return "events" in tables and "nodes" not in tables
    finally:
        conn.close()


def run_migration() -> int:
    """Convert v1 events to v2 nodes. Returns count of rows migrated."""
    db_path = _get_db_path()
    if not db_path.exists():
        return 0
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        if "events" not in tables:
            return 0

        # Ensure nodes table exists
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

        events = conn.execute("SELECT * FROM events").fetchall()
        migrated = 0
        for e in events:
            node_id = f"migrated-event-{e['id']}"
            exists = conn.execute(
                "SELECT id FROM nodes WHERE id = ?", (node_id,)
            ).fetchone()
            if exists:
                continue
            fields = {
                "story": e["story"],
                "world_date": e["world_date"],
                "location": e["location"] or "",
                "characters": json.loads(e["characters"] or "[]"),
                "summary": e["summary"],
                "tags": json.loads(e["tags"] or "[]"),
            }
            conn.execute(
                "INSERT INTO nodes (id, type, fields, created) VALUES (?, ?, ?, ?)",
                (node_id, "event", json.dumps(fields), e["created_at"])
            )
            migrated += 1
        conn.commit()
        return migrated
    finally:
        conn.close()
