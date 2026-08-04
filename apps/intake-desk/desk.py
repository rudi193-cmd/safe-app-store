"""The desk operations.

Six states, one hard rule per transition (spec §3):

    filed -> routed -> ruled -> published
                         |
                         +-> withheld     (consent revoked / narrator asked)
    (any)  ------------------> uncheckable (terminal, and a success)

There is no delete. `withhold` is the operation.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

import consent as consent_mod
from desk_db import body_digest

MEDIA = ("audio", "transcript", "typed", "letter", "note")
SOURCE_TYPES = ("public_record", "oral_history_consented", "authored", "unverifiable")


class DeskError(Exception):
    """A refusal. Always fail-closed — the desk declines rather than guesses."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _id() -> str:
    return uuid.uuid4().hex


# ── filing ────────────────────────────────────────────────────────────────────

def file_statement(
    conn: sqlite3.Connection,
    *,
    consent_store: Path | str,
    session_id: str,
    narrator_id: str,
    taker_id: str,
    body: str,
    medium: str = "transcript",
    captured_at: str | None = None,
) -> str:
    """Record what a person said, verbatim and whole.

    Refuses without a verified keeping grant for the narrator. A statement
    filed without consent is not a statement — it is a recording somebody
    made of a person who did not agree to it.
    """
    if medium not in MEDIA:
        raise DeskError(f"unknown medium: {medium!r}")
    if not body.strip():
        raise DeskError("a statement with no body is not a statement")
    if not consent_mod.may_keep(consent_store, narrator_id):
        raise DeskError(
            f"no verified keeping consent for narrator {narrator_id!r} — "
            "absence is not consent"
        )

    sid = _id()
    conn.execute(
        "INSERT INTO statements (id, created_at, session_id, narrator_id, taker_id,"
        " body, medium, captured_at, consent_ref, body_sha256)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)",
        (sid, _now(), session_id, narrator_id, taker_id, body, medium,
         captured_at, narrator_id, body_digest(body)),
    )
    conn.commit()
    consent_mod.note_disclosure(
        consent_store, narrator_id, "statement_filed", f"session={session_id} id={sid}"
    )
    return sid


def add_claim(
    conn: sqlite3.Connection,
    *,
    statement_id: str,
    span: tuple[int, int],
    assertion: str,
    source_type: str = "oral_history_consented",
    entities: list | None = None,
    occurred_at: str | None = None,
    place: str | None = None,
) -> str:
    """Break one checkable assertion out of a statement.

    The span is not decoration — a claim that cannot point back at the words
    it came from is refused by the schema, not by this function.
    """
    if source_type not in SOURCE_TYPES:
        raise DeskError(f"unknown source_type: {source_type!r}")
    cid = _id()
    try:
        conn.execute(
            "INSERT INTO claims (id, statement_id, span_start, span_end, assertion,"
            " entities, occurred_at, place, state, source_type)"
            " VALUES (?,?,?,?,?,?,?,?,'filed',?)",
            (cid, statement_id, span[0], span[1], assertion,
             json.dumps(entities or []), occurred_at, place, source_type),
        )
    except sqlite3.IntegrityError as exc:
        raise DeskError(str(exc)) from exc
    conn.commit()
    return cid


def quoted(conn: sqlite3.Connection, claim_id: str) -> str:
    """The words a claim was drawn from. The receipt behind every assertion."""
    row = conn.execute(
        "SELECT s.body, c.span_start, c.span_end FROM claims c"
        " JOIN statements s ON s.id = c.statement_id WHERE c.id = ?",
        (claim_id,),
    ).fetchone()
    if row is None:
        raise DeskError(f"no such claim: {claim_id!r}")
    return row["body"][row["span_start"]:row["span_end"]]


# ── the docket ────────────────────────────────────────────────────────────────

def add_docket_entry(
    conn: sqlite3.Connection,
    *,
    claim_id: str,
    relation: str,
    source_kind: str,
    found_by: str,
    source_ref: str | None = None,
    excerpt: str | None = None,
) -> str:
    """Record evidence for or against a claim. Never a verdict."""
    eid = _id()
    try:
        conn.execute(
            "INSERT INTO docket_entries (id, claim_id, created_at, relation,"
            " source_kind, source_ref, excerpt, found_by) VALUES (?,?,?,?,?,?,?,?)",
            (eid, claim_id, _now(), relation, source_kind, source_ref, excerpt, found_by),
        )
    except sqlite3.IntegrityError as exc:
        raise DeskError(str(exc)) from exc
    conn.execute("UPDATE claims SET state='routed' WHERE id=? AND state='filed'", (claim_id,))
    conn.commit()
    return eid


def docket(conn: sqlite3.Connection, claim_id: str) -> list[sqlite3.Row]:
    return list(conn.execute(
        "SELECT * FROM docket_entries WHERE claim_id=? ORDER BY created_at", (claim_id,)
    ))


# ── ruling ────────────────────────────────────────────────────────────────────

def rule(
    conn: sqlite3.Connection,
    *,
    claim_id: str,
    ruled_by: str,
    confidence: str,
    note: str = "",
) -> None:
    """A human judges a claim.

    §0.2: proposing and ratifying never rest in the same hand. The ruler may
    be neither the narrator nor the taker — enforced by the schema, so it
    holds for any writer, not just this one. There is no override flag.
    """
    if confidence not in ("high", "medium", "low", "conflicting"):
        raise DeskError(f"unknown confidence: {confidence!r}")
    try:
        cur = conn.execute(
            "UPDATE claims SET ruled_by=?, ruled_at=?, ruling_note=?,"
            " confidence=?, state='ruled' WHERE id=? AND state IN ('filed','routed')",
            (ruled_by, _now(), note, confidence, claim_id),
        )
    except sqlite3.IntegrityError as exc:
        raise DeskError(str(exc)) from exc
    if cur.rowcount == 0:
        raise DeskError(f"claim {claim_id!r} is not in a rulable state")
    conn.commit()


def mark_uncheckable(conn: sqlite3.Connection, *, claim_id: str, ruled_by: str, note: str = "") -> None:
    """Terminal, and a success.

    No source class could exist for this claim — a first-person feeling, a
    private moment, a room with two people in it and one of them is dead.
    Confirming the gap is real is work, and this is what it produces.
    """
    try:
        cur = conn.execute(
            "UPDATE claims SET ruled_by=?, ruled_at=?, ruling_note=?,"
            " source_type='unverifiable', state='uncheckable' WHERE id=?",
            (ruled_by, _now(), note, claim_id),
        )
    except sqlite3.IntegrityError as exc:
        raise DeskError(str(exc)) from exc
    if cur.rowcount == 0:
        raise DeskError(f"no such claim: {claim_id!r}")
    conn.commit()


def publish(conn: sqlite3.Connection, *, claim_id: str) -> None:
    """Mark a ruled claim as permitted to leave the vault.

    "Published" means *may leave*, not *is now a webpage*. The consent check
    happens again at egress (export.py) — a grant can be withdrawn between
    here and there, and the later check is the one that counts.
    """
    cur = conn.execute(
        "UPDATE claims SET state='published' WHERE id=? AND state='ruled'", (claim_id,)
    )
    if cur.rowcount == 0:
        raise DeskError(f"claim {claim_id!r} is not ruled — nothing to publish")
    conn.commit()


def withhold(conn: sqlite3.Connection, *, claim_id: str, reason: str = "") -> None:
    """Stop the export. Keep the record. Never a delete."""
    corrections = conn.execute(
        "SELECT corrections FROM claims WHERE id=?", (claim_id,)
    ).fetchone()
    if corrections is None:
        raise DeskError(f"no such claim: {claim_id!r}")
    log = json.loads(corrections["corrections"])
    log.append({"at": _now(), "action": "withheld", "reason": reason})
    conn.execute(
        "UPDATE claims SET state='withheld', corrections=? WHERE id=?",
        (json.dumps(log), claim_id),
    )
    conn.commit()


def withhold_narrator(conn: sqlite3.Connection, *, narrator_id: str, reason: str = "") -> int:
    """Withhold everything a narrator gave. What revocation actually does."""
    rows = conn.execute(
        "SELECT c.id FROM claims c JOIN statements s ON s.id = c.statement_id"
        " WHERE s.narrator_id = ? AND c.state != 'withheld'",
        (narrator_id,),
    ).fetchall()
    for row in rows:
        withhold(conn, claim_id=row["id"], reason=reason)
    return len(rows)


# ── the queue ─────────────────────────────────────────────────────────────────

def queue(conn: sqlite3.Connection) -> dict[str, int]:
    """What a human is uniquely needed for, ordered by that (spec §7)."""
    counts = {"contradicted": 0, "uncorroborated": 0, "uncheckable": 0, "corroborated": 0}
    rows = conn.execute(
        "SELECT c.id, c.state,"
        " SUM(CASE WHEN d.relation='contradicts' THEN 1 ELSE 0 END) AS against,"
        " SUM(CASE WHEN d.relation='corroborates' THEN 1 ELSE 0 END) AS for_"
        " FROM claims c LEFT JOIN docket_entries d ON d.claim_id = c.id"
        " WHERE c.state IN ('filed','routed','uncheckable') GROUP BY c.id"
    )
    for row in rows:
        if row["state"] == "uncheckable":
            counts["uncheckable"] += 1
        elif row["against"]:
            counts["contradicted"] += 1
        elif row["for_"]:
            counts["corroborated"] += 1
        else:
            counts["uncorroborated"] += 1
    return counts
