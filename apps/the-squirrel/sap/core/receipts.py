"""
sap.core.receipts — append-only audit trail for every Squirrel tool call.
b17: NNA92
ΔΣ=42

Schema is verbatim willow-data-vault/schema/03_receipts.sql (itself extracted
from willow-mcp receipts.py). When the Squirrel talks to a willow-mcp server,
receipts are automatic on the server side; when it talks to anything else —
who knows. So the Squirrel writes its own, locally, in the vault's schema:
the trail exists no matter whose server is on the other end.

One row per call regardless of outcome (ok / denied / bypass / error).
app_id holds the acting identity (squirrel-journal, squirrel-jeles,
operator-bypass, unattributed) — this is a single-operator box, so unlike
willow-mcp's multi-tenant tail, the operator may read the whole trail.
Sensitive, and it stays in the box.

Dedicated SQLite connection — never shares the app's db connections, so a
busy receipt log can't stall a PII call or vice versa.
"""

import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS receipts (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      TEXT NOT NULL,
    app_id  TEXT NOT NULL,
    tool    TEXT NOT NULL,
    outcome TEXT NOT NULL,
    detail  TEXT
);
CREATE INDEX IF NOT EXISTS idx_receipts_ts     ON receipts(ts DESC);
CREATE INDEX IF NOT EXISTS idx_receipts_app_id ON receipts(app_id);
"""


class ReceiptLog:
    """Append-only SQLite log of every tool call."""

    def __init__(self, db_path=None):
        from sap.core.vault import squirrel_home
        self.path = Path(db_path or os.environ.get(
            "SQUIRREL_RECEIPT_DB", squirrel_home() / "receipts.db"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def record(self, app_id, tool, outcome, detail=None):
        ts = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._conn.execute(
                "INSERT INTO receipts (ts, app_id, tool, outcome, detail) "
                "VALUES (?, ?, ?, ?, ?)",
                (ts, app_id, tool, outcome, detail))
            self._conn.commit()

    def tail(self, app_id=None, limit=20):
        """Most-recent receipts, newest first. app_id=None returns the whole
        trail — the operator owns this box and every identity in it."""
        limit = max(1, min(int(limit), 200))
        query = "SELECT ts, app_id, tool, outcome, detail FROM receipts "
        params = []
        if app_id is not None:
            query += "WHERE app_id = ? "
            params.append(app_id)
        query += "ORDER BY id DESC LIMIT ?"
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        return [{"ts": r[0], "app_id": r[1], "tool": r[2],
                 "outcome": r[3], "detail": r[4]} for r in rows]

    def close(self):
        with self._lock:
            self._conn.close()


_log = None
_log_lock = threading.Lock()


def log() -> ReceiptLog:
    global _log
    if _log is None:
        with _log_lock:
            if _log is None:
                _log = ReceiptLog()
    return _log


def record(app_id, tool, outcome, detail=None):
    log().record(app_id, tool, outcome, detail)


def tail(app_id=None, limit=20):
    return log().tail(app_id=app_id, limit=limit)


def reset():
    """Drop the singleton (tests: re-point SQUIRREL_RECEIPT_DB, then reset)."""
    global _log
    with _log_lock:
        if _log is not None:
            _log.close()
        _log = None
