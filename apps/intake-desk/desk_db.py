"""Storage for the intake desk.

Local-first SQLite. The schema (schema.sql) carries the invariants as
triggers, so they hold for anything that opens the file — not only for code
that goes through desk.py.
"""
from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from vault_paths import resolve  # shared vault-rooted resolver (box audit A5)

SCHEMA = Path(__file__).with_name("schema.sql")


def default_db() -> Path:
    """Where a desk keeps its vault.

    Derived from the vault root, never a hardcoded home path (installer design
    D7/D8). A desk is somebody's desk — there is no central pile — so the
    operator can point this anywhere with INTAKE_DESK_DB.
    """
    return resolve("intake-desk", "desk.sqlite3", env_vars=("INTAKE_DESK_DB",))


def body_digest(body: str) -> str:
    """The tamper witness stored beside a verbatim statement."""
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def connect(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Open (creating if needed) a desk vault with the schema applied."""
    path = Path(db_path) if db_path is not None else default_db()
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def verify_bodies(conn: sqlite3.Connection) -> list[str]:
    """Return the ids of statements whose body no longer matches its digest.

    The write-once trigger stops the ordinary path; this catches a body
    rewritten by something that bypassed it (a direct sqlite3 session with
    triggers dropped, a restored partial backup). Empty list means clean.
    """
    bad = []
    for row in conn.execute("SELECT id, body, body_sha256 FROM statements"):
        if body_digest(row["body"]) != row["body_sha256"]:
            bad.append(row["id"])
    return bad
