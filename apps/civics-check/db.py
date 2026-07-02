"""Local SQLite persistence for civics-check: scores and missed-question tracking."""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "civics_check.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS missed_questions (
    question_id INTEGER PRIMARY KEY,
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


def record_miss(question_id):
    conn = connect()
    conn.execute(
        """INSERT INTO missed_questions (question_id, miss_count, last_missed)
           VALUES (?, 1, datetime('now'))
           ON CONFLICT(question_id) DO UPDATE SET
               miss_count = miss_count + 1,
               last_missed = datetime('now')""",
        (question_id,),
    )
    conn.commit()
    conn.close()


def missed_question_ids(limit=None):
    conn = connect()
    query = "SELECT question_id FROM missed_questions ORDER BY miss_count DESC, last_missed DESC"
    if limit:
        query += f" LIMIT {int(limit)}"
    rows = conn.execute(query).fetchall()
    conn.close()
    return [r[0] for r in rows]


def clear_miss(question_id):
    conn = connect()
    conn.execute("DELETE FROM missed_questions WHERE question_id = ?", (question_id,))
    conn.commit()
    conn.close()


def record_score(mode, score, total, elapsed_s=None):
    conn = connect()
    conn.execute(
        "INSERT INTO scores (mode, score, total, elapsed_s) VALUES (?, ?, ?, ?)",
        (mode, score, total, elapsed_s),
    )
    conn.commit()
    conn.close()


def top_scores(mode, limit=5):
    conn = connect()
    rows = conn.execute(
        """SELECT score, total, elapsed_s, played_at FROM scores
           WHERE mode = ? ORDER BY score DESC, elapsed_s ASC LIMIT ?""",
        (mode, limit),
    ).fetchall()
    conn.close()
    return rows
