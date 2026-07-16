"""
sap.core.gaps — the acknowledged-unknowns ledger.
b17: NNA92
ΔΣ=42

The Squirrel signs every file ΔΣ=42 — "42 acknowledged unknowns" — but until
now it acknowledged none: a miss ("Person not found", an ambiguous bind) was
said once and forgotten. This is the memory. Modeled on ask-jeles's gap
backlog (askjeles/corpus.py log_gap): a miss becomes a tracked gap, repeated
misses bump a count instead of duplicating, and gaps are worked down over time.

ONE deliberate divergence from Jeles, and it's the whole point: **Jeles
forwards its gaps to willow-mcp's fleet-wide backlog; the Squirrel never
does.** Jeles's gaps are public-knowledge questions ("what is a Vespa?"); the
Squirrel's gaps name family members ("unknown person: Oscar Mann's father") —
that is PII. Forwarding it would send the tree off the box and break the
zero-egress invariant tests/test_chokepoint.py enforces. So this ledger is
local, in the box, and stays there — the same reason Wikipedia is a link and
not a fetch. The tree stays in the tree; so do the questions about it.

Kinds:
  unknown_person    — a name referenced (link/tree/kin) that isn't in the tree
  ambiguous_bind    — a fragment that matched several people; needs a human

Store: $SQUIRREL_HOME/gaps.db (override: SQUIRREL_GAPS_DB). Holds family
names — 0600, in the 0700 box, never forwarded.
"""

import os
import re
import sqlite3
import threading
import uuid
from datetime import datetime, timezone

_SCHEMA = """
CREATE TABLE IF NOT EXISTS gaps (
    id          TEXT PRIMARY KEY,
    kind        TEXT NOT NULL,
    subject     TEXT NOT NULL,
    detail      TEXT,
    asked_count INTEGER NOT NULL DEFAULT 1,
    status      TEXT NOT NULL DEFAULT 'open',
    first_seen  TEXT NOT NULL,
    last_seen   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_gaps_status ON gaps(status);
"""

VALID_KINDS = frozenset({"unknown_person", "ambiguous_bind"})


def _now():
    return datetime.now(timezone.utc).isoformat()


def _norm(subject: str) -> str:
    return re.sub(r"\s+", " ", (subject or "").strip().lower())


def _key(kind: str, subject: str) -> str:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"{kind}|{_norm(subject)}").hex[:12]


class GapLog:
    def __init__(self, db_path=None):
        from sap.core.vault import squirrel_home
        self.path = str(db_path or os.environ.get(
            "SQUIRREL_GAPS_DB", squirrel_home() / "gaps.db"))
        if self.path != ":memory:":
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        if os.path.exists(self.path) and self.path != ":memory:":
            try:
                os.chmod(self.path, 0o600)
            except OSError:
                pass

    def log(self, kind: str, subject: str, detail: str = None) -> dict:
        """Record a gap. A repeated miss bumps asked_count; a re-asked gap that
        was resolved reopens — you're asking again, so it's open again."""
        if kind not in VALID_KINDS or not (subject or "").strip():
            return {}
        gid = _key(kind, subject)
        now = _now()
        with self._lock:
            row = self._conn.execute(
                "SELECT asked_count FROM gaps WHERE id = ?", (gid,)).fetchone()
            if row is None:
                self._conn.execute(
                    "INSERT INTO gaps (id, kind, subject, detail, asked_count, "
                    "status, first_seen, last_seen) VALUES (?,?,?,?,1,'open',?,?)",
                    (gid, kind, subject.strip(), detail, now, now))
                count = 1
            else:
                count = row[0] + 1
                self._conn.execute(
                    "UPDATE gaps SET asked_count = ?, status = 'open', "
                    "last_seen = ?, detail = COALESCE(?, detail) WHERE id = ?",
                    (count, now, detail, gid))
            self._conn.commit()
        return {"id": gid, "asked_count": count}

    def list_open(self, limit: int = 50) -> list:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, kind, subject, detail, asked_count, first_seen, last_seen "
                "FROM gaps WHERE status = 'open' "
                "ORDER BY asked_count DESC, last_seen DESC LIMIT ?",
                (max(1, min(int(limit), 500)),)).fetchall()
        cols = ["id", "kind", "subject", "detail", "asked_count", "first_seen", "last_seen"]
        return [dict(zip(cols, r)) for r in rows]

    def count_open(self) -> int:
        with self._lock:
            return self._conn.execute(
                "SELECT COUNT(*) FROM gaps WHERE status = 'open'").fetchone()[0]

    def resolve(self, gap_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "UPDATE gaps SET status = 'resolved', last_seen = ? "
                "WHERE id = ? AND status = 'open'", (_now(), gap_id))
            self._conn.commit()
            return cur.rowcount > 0

    def resolve_subject(self, kind: str, subject: str) -> int:
        """Resolve open gaps of a kind matching a subject — the loop-closer:
        when the unknown person is finally added, the gap that named them
        resolves itself."""
        gid = _key(kind, subject)
        with self._lock:
            cur = self._conn.execute(
                "UPDATE gaps SET status = 'resolved', last_seen = ? "
                "WHERE id = ? AND status = 'open'", (_now(), gid))
            self._conn.commit()
            return cur.rowcount

    def close(self):
        with self._lock:
            self._conn.close()


_log = None
_log_lock = threading.Lock()


def _get() -> GapLog:
    global _log
    if _log is None:
        with _log_lock:
            if _log is None:
                _log = GapLog()
    return _log


def log(kind, subject, detail=None):
    return _get().log(kind, subject, detail)


def list_open(limit=50):
    return _get().list_open(limit)


def count_open():
    return _get().count_open()


def resolve(gap_id):
    return _get().resolve(gap_id)


def resolve_subject(kind, subject):
    return _get().resolve_subject(kind, subject)


def reset():
    """Drop the singleton (tests re-point SQUIRREL_GAPS_DB, then reset)."""
    global _log
    with _log_lock:
        if _log is not None:
            _log.close()
        _log = None
