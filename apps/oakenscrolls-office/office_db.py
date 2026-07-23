"""
office_db.py — the append-only prediction ledger. b17: OAKOF

The rules live here, not in the UI:
  * Predictions are immutable facts of statement — no UPDATE, no DELETE, ever.
    Everything that happens afterward is an appended event; current state is
    derived, never stored (willow-mcp commitment-membrane discipline).
  * Confidence is P(true) in [0.5, 0.99]: state the claim in the direction you
    believe (design D3). The ledger refuses hedged-backwards entries loudly.
  * VOID keeps its record. States-not-deletions.

In the no-egress zone: no network imports (tests/test_no_egress.py).
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from typing import Optional

from office_paths import db_path

CONF_MIN, CONF_MAX = 0.5, 0.99


def _db() -> sqlite3.Connection:
    path = db_path()  # resolved per call, so tests can point elsewhere
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS predictions (
            id         TEXT PRIMARY KEY,
            claim      TEXT NOT NULL,
            confidence REAL NOT NULL,
            stated_at  INTEGER NOT NULL,
            due        INTEGER,
            tags       TEXT NOT NULL DEFAULT '[]'
        );
        CREATE TABLE IF NOT EXISTS events (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            prediction_id TEXT NOT NULL REFERENCES predictions(id),
            kind          TEXT NOT NULL,
            confidence    REAL,
            outcome       INTEGER,
            note          TEXT,
            evidence      TEXT,
            at            INTEGER NOT NULL
        );
    """)
    # v0.1 ledgers predate the evidence column; append it in place (the table
    # itself is append-only, so ALTER ADD COLUMN is the only migration kind
    # this schema will ever need).
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(events)")}
    if "evidence" not in cols:
        conn.execute("ALTER TABLE events ADD COLUMN evidence TEXT")
    conn.commit()
    return conn


def _check_confidence(confidence: float) -> float:
    if not (CONF_MIN <= confidence <= CONF_MAX):
        raise ValueError(
            f"confidence must be in [{CONF_MIN}, {CONF_MAX}] — "
            "state the claim in the direction you believe"
        )
    return float(confidence)


def state_claim(
    claim: str,
    confidence: float,
    due: Optional[int] = None,
    tags: tuple[str, ...] = (),
) -> str:
    """Put a belief on the record. Returns the prediction id."""
    claim = claim.strip()
    if not claim:
        raise ValueError("a claim must say something")
    _check_confidence(confidence)
    pid = uuid.uuid4().hex[:8]
    with _db() as c:
        c.execute(
            "INSERT INTO predictions (id, claim, confidence, stated_at, due, tags) "
            "VALUES (?,?,?,?,?,?)",
            (pid, claim, confidence, int(time.time()), due, json.dumps(list(tags))),
        )
    return pid


def _append(pid: str, kind: str, confidence=None, outcome=None, note=None, evidence=None) -> None:
    with _db() as c:
        exists = c.execute("SELECT 1 FROM predictions WHERE id=?", (pid,)).fetchone()
        if not exists:
            raise KeyError(pid)
        c.execute(
            "INSERT INTO events (prediction_id, kind, confidence, outcome, note, evidence, at) "
            "VALUES (?,?,?,?,?,?,?)",
            (pid, kind, confidence, outcome, note,
             json.dumps(evidence) if evidence is not None else None, int(time.time())),
        )


def revise(pid: str, confidence: float) -> None:
    """Change your mind before the world weighs in. The old number stays on
    the record; only an open prediction can be revised."""
    _check_confidence(confidence)
    if current(pid)["status"] != "open":
        raise ValueError("only an open prediction can be revised")
    _append(pid, "revised", confidence=confidence)


def resolve(
    pid: str,
    outcome: bool,
    note: Optional[str] = None,
    evidence: Optional[dict] = None,
) -> None:
    """Grade a prediction. `evidence` is an optional citation record (e.g.
    almanac_seam.citation()) pinned to the resolving event forever."""
    if current(pid)["status"] != "open":
        raise ValueError("only an open prediction can be resolved")
    _append(pid, "resolved", outcome=1 if outcome else 0, note=note, evidence=evidence)


def void(pid: str, note: Optional[str] = None) -> None:
    """The claim turned out unresolvable or ambiguous. The record is kept."""
    if current(pid)["status"] != "open":
        raise ValueError("only an open prediction can be voided")
    _append(pid, "voided", note=note)


def reopen(pid: str, note: Optional[str] = None) -> None:
    if current(pid)["status"] == "open":
        raise ValueError("prediction is already open")
    _append(pid, "reopened", note=note)


def _derive(pred: sqlite3.Row, events: list[sqlite3.Row]) -> dict:
    """Fold the event log into current state. Derived, never stored."""
    status = "open"
    confidence = pred["confidence"]
    outcome = None
    resolved_at = None
    evidence = None
    for e in events:  # chronological
        if e["kind"] == "revised":
            confidence = e["confidence"]
        elif e["kind"] == "resolved":
            status, outcome, resolved_at = "resolved", bool(e["outcome"]), e["at"]
            evidence = json.loads(e["evidence"]) if e["evidence"] else None
        elif e["kind"] == "voided":
            status, outcome, resolved_at, evidence = "voided", None, e["at"], None
        elif e["kind"] == "reopened":
            status, outcome, resolved_at, evidence = "open", None, None, None
    return {
        "id": pred["id"],
        "claim": pred["claim"],
        "confidence": confidence,
        "stated_confidence": pred["confidence"],
        "stated_at": pred["stated_at"],
        "due": pred["due"],
        "tags": json.loads(pred["tags"]),
        "status": status,
        "outcome": outcome,
        "resolved_at": resolved_at,
        "evidence": evidence,
        "revisions": sum(1 for e in events if e["kind"] == "revised"),
    }


def current(pid: str) -> dict:
    with _db() as c:
        pred = c.execute("SELECT * FROM predictions WHERE id=?", (pid,)).fetchone()
        if not pred:
            raise KeyError(pid)
        events = c.execute(
            "SELECT * FROM events WHERE prediction_id=? ORDER BY id", (pid,)
        ).fetchall()
    return _derive(pred, events)


def ledger(status: Optional[str] = None) -> list[dict]:
    """All predictions (derived state), newest statement first."""
    with _db() as c:
        preds = c.execute("SELECT * FROM predictions ORDER BY stated_at DESC").fetchall()
        events = c.execute("SELECT * FROM events ORDER BY id").fetchall()
    by_pid: dict[str, list] = {}
    for e in events:
        by_pid.setdefault(e["prediction_id"], []).append(e)
    rows = [_derive(p, by_pid.get(p["id"], [])) for p in preds]
    return [r for r in rows if r["status"] == status] if status else rows


def due_now(now: Optional[int] = None) -> list[dict]:
    """Open predictions whose due date has arrived — the dew. Oldest due first."""
    now = int(time.time()) if now is None else now
    due = [r for r in ledger("open") if r["due"] is not None and r["due"] <= now]
    return sorted(due, key=lambda r: r["due"])


def resolved_pairs() -> list[tuple[float, bool]]:
    """(final confidence, outcome) for every resolved prediction — the input
    to calibration.py. Latest confidence before resolution is what gets scored
    (design D2); voided predictions never enter the score."""
    return [(r["confidence"], r["outcome"]) for r in ledger("resolved")]
