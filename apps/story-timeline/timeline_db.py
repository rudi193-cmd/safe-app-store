"""
timeline_db.py — SQLite backend for story-timeline.
Events: in-world date, location, characters, summary, tags.
"""
import json
import sqlite3
from pathlib import Path

DB_PATH = Path.home() / ".willow" / "store" / "story-timeline" / "timeline.db"


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            story       TEXT NOT NULL DEFAULT 'default',
            world_date  TEXT NOT NULL,
            location    TEXT DEFAULT '',
            characters  TEXT DEFAULT '[]',
            summary     TEXT NOT NULL,
            tags        TEXT DEFAULT '[]',
            created_at  TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    return conn


def add_event(story: str, world_date: str, summary: str,
              location: str = "", characters: list = None, tags: list = None) -> int:
    conn = _conn()
    cur = conn.execute(
        "INSERT INTO events (story, world_date, location, characters, summary, tags) VALUES (?,?,?,?,?,?)",
        (story, world_date, location,
         json.dumps(characters or []), summary, json.dumps(tags or []))
    )
    conn.commit()
    row_id = cur.lastrowid
    conn.close()
    return row_id


def get_events(story: str = None, character: str = None) -> list[dict]:
    conn = _conn()
    if story:
        rows = conn.execute(
            "SELECT * FROM events WHERE story = ? ORDER BY world_date ASC", (story,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM events ORDER BY world_date ASC"
        ).fetchall()
    conn.close()
    events = []
    for r in rows:
        e = dict(r)
        e["characters"] = json.loads(e["characters"])
        e["tags"] = json.loads(e["tags"])
        if character and character.lower() not in [c.lower() for c in e["characters"]]:
            continue
        events.append(e)
    return events


def get_stories() -> list[str]:
    conn = _conn()
    rows = conn.execute(
        "SELECT DISTINCT story FROM events ORDER BY story"
    ).fetchall()
    conn.close()
    return [r[0] for r in rows] or ["default"]


def delete_event(event_id: int) -> bool:
    conn = _conn()
    cur = conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def export_markdown(story: str = None) -> str:
    events = get_events(story=story)
    if not events:
        return "_No events recorded yet._"
    lines = [f"# Timeline{f': {story}' if story else ''}\n"]
    for e in events:
        chars = ", ".join(e["characters"]) if e["characters"] else "—"
        lines.append(f"## {e['world_date']}")
        lines.append(f"**Location:** {e['location'] or '—'}  ")
        lines.append(f"**Characters:** {chars}  ")
        lines.append(f"\n{e['summary']}\n")
    return "\n".join(lines)
