"""
Per-professor SQLite session persistence for UTETY TUI.
Each professor gets their own DB at data/sessions/<slug>.db.
Professors remember across restarts.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

_DB_DIR = Path(__file__).parent / "data" / "sessions"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    role     TEXT    NOT NULL,
    content  TEXT    NOT NULL,
    provider TEXT    DEFAULT '',
    ts       TEXT    NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


def _slug(professor: str) -> str:
    return professor.lower().replace(" ", "_")


def _db_path(professor: str) -> Path:
    _DB_DIR.mkdir(parents=True, exist_ok=True)
    return _DB_DIR / f"{_slug(professor)}.db"


def _connect(professor: str) -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path(professor))
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def load_history(professor: str) -> list[dict]:
    conn = _connect(professor)
    rows = conn.execute(
        "SELECT role, content, provider, ts FROM messages ORDER BY id"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_message(professor: str, role: str, content: str, provider: str = "") -> None:
    conn = _connect(professor)
    conn.execute(
        "INSERT INTO messages (role, content, provider, ts) VALUES (?, ?, ?, ?)",
        (role, content, provider, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def clear_history(professor: str) -> None:
    conn = _connect(professor)
    conn.execute("DELETE FROM messages")
    conn.commit()
    conn.close()


def get_meta(professor: str, key: str, default: str = "") -> str:
    conn = _connect(professor)
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def set_meta(professor: str, key: str, value: str) -> None:
    conn = _connect(professor)
    conn.execute(
        "INSERT INTO meta (key, value) VALUES (?, ?)"
        " ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
    conn.commit()
    conn.close()


def message_count(professor: str) -> int:
    conn = _connect(professor)
    n = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    conn.close()
    return n


def export_markdown(professor: str) -> str:
    history = load_history(professor)
    lines = [f"# Conversation with {professor}", ""]
    for msg in history:
        label = "**You**" if msg["role"] == "user" else f"**{professor}**"
        lines.append(f"{label}: {msg['content']}")
        lines.append("")
    return "\n".join(lines)
