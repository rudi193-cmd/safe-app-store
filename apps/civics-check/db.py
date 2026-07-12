"""Local SQLite persistence: scores and spaced-repetition misses."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from civics.paths import app_root
from civics_paths import app_data


def _db_path() -> Path:
    """Scores DB beside app in dev; vault-rooted (D8) when installed as a package."""
    root = app_root()
    if (root / "safe-app-manifest.json").exists() or (root / "scripts").is_dir():
        return root / "civics_check.db"
    store = app_data()
    store.mkdir(parents=True, exist_ok=True)
    return store / "civics_check.db"


DB_PATH = _db_path()

SCHEMA = """
CREATE TABLE IF NOT EXISTS missed_questions (
    question_id INTEGER PRIMARY KEY,
    miss_count INTEGER NOT NULL DEFAULT 0,
    last_missed TEXT
);

CREATE TABLE IF NOT EXISTS card_misses (
    card_id TEXT PRIMARY KEY,
    miss_count INTEGER NOT NULL DEFAULT 0,
    last_missed TEXT
);

CREATE TABLE IF NOT EXISTS scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mode TEXT NOT NULL,
    score INTEGER NOT NULL,
    total INTEGER NOT NULL,
    elapsed_s REAL,
    played_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    return conn


def record_miss(question_id: int | str):
    """Record a miss — accepts legacy int USCIS id or card_id string."""
    conn = connect()
    card_id = None
    if isinstance(question_id, int) or (isinstance(question_id, str) and question_id.isdigit()):
        qid = int(question_id)
        conn.execute(
            """INSERT INTO missed_questions (question_id, miss_count, last_missed)
               VALUES (?, 1, datetime('now'))
               ON CONFLICT(question_id) DO UPDATE SET
                   miss_count = miss_count + 1,
                   last_missed = datetime('now')""",
            (qid,),
        )
        card_id = f"nat-{qid:03d}"
    else:
        card_id = str(question_id)
        if card_id.startswith("nat-"):
            try:
                qid = int(card_id.split("-", 1)[1])
                conn.execute(
                    """INSERT INTO missed_questions (question_id, miss_count, last_missed)
                       VALUES (?, 1, datetime('now'))
                       ON CONFLICT(question_id) DO UPDATE SET
                           miss_count = miss_count + 1,
                           last_missed = datetime('now')""",
                    (qid,),
                )
            except ValueError:
                pass
    if card_id and card_id.startswith("nat-"):
        conn.execute(
            """INSERT INTO card_misses (card_id, miss_count, last_missed)
               VALUES (?, 1, datetime('now'))
               ON CONFLICT(card_id) DO UPDATE SET
                   miss_count = miss_count + 1,
                   last_missed = datetime('now')""",
            (card_id,),
        )
    conn.commit()
    conn.close()


def missed_question_ids(limit: int | None = None) -> list[int]:
    conn = connect()
    query = "SELECT question_id FROM missed_questions ORDER BY miss_count DESC, last_missed DESC"
    if limit:
        query += f" LIMIT {int(limit)}"
    rows = conn.execute(query).fetchall()
    conn.close()
    return [r[0] for r in rows]


def missed_card_ids(limit: int | None = None) -> list[str]:
    conn = connect()
    query = "SELECT card_id FROM card_misses ORDER BY miss_count DESC, last_missed DESC"
    if limit:
        query += f" LIMIT {int(limit)}"
    rows = conn.execute(query).fetchall()
    conn.close()
    return [r[0] for r in rows]


def clear_miss(question_id: int | str):
    conn = connect()
    card_id = None
    if isinstance(question_id, int) or (isinstance(question_id, str) and question_id.isdigit()):
        qid = int(question_id)
        conn.execute("DELETE FROM missed_questions WHERE question_id = ?", (qid,))
        card_id = f"nat-{qid:03d}"
    else:
        card_id = str(question_id)
        if card_id.startswith("nat-"):
            try:
                qid = int(card_id.split("-", 1)[1])
                conn.execute("DELETE FROM missed_questions WHERE question_id = ?", (qid,))
            except ValueError:
                pass
    if card_id and card_id.startswith("nat-"):
        conn.execute("DELETE FROM card_misses WHERE card_id = ?", (card_id,))
    conn.commit()
    conn.close()


def record_score(mode: str, score: int, total: int, elapsed_s: float | None = None):
    conn = connect()
    conn.execute(
        "INSERT INTO scores (mode, score, total, elapsed_s) VALUES (?, ?, ?, ?)",
        (mode, score, total, elapsed_s),
    )
    conn.commit()
    conn.close()


def top_scores(mode: str, limit: int = 5):
    conn = connect()
    rows = conn.execute(
        """SELECT score, total, elapsed_s, played_at FROM scores
           WHERE mode = ? ORDER BY score DESC, elapsed_s ASC LIMIT ?""",
        (mode, limit),
    ).fetchall()
    conn.close()
    return rows
