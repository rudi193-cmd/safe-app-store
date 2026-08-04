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
import vocabulary
from desk_db import body_digest
from entities import extract_entities

MEDIA = ("audio", "transcript", "typed", "letter", "note")
SOURCE_TYPES = ("public_record", "oral_history_consented", "authored", "unverifiable")


class DeskError(Exception):
    """A refusal. Always fail-closed — the desk declines rather than guesses."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _id() -> str:
    return uuid.uuid4().hex


def identity(value: str, *, field: str = "identity") -> str:
    """Normalise a person's identifier, or refuse it.

    The witness gate compares identity strings, and SQLite compares TEXT
    byte-exactly. Without this, `Slappy` sailed through a gate that refused
    `slappy`, and a whitespace-only ruler was accepted — the keystone gate
    defeated by a shift key. Every identity enters the vault through here.
    """
    if value is None:
        raise DeskError(f"{field} is required")
    normalised = " ".join(str(value).split()).strip().lower()
    if not normalised:
        raise DeskError(f"{field} is required — an unnamed hand is not a witness")
    return normalised


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
    narrator_id = identity(narrator_id, field="narrator_id")
    taker_id = identity(taker_id, field="taker_id")
    if not consent_mod.may_keep(consent_store, narrator_id):
        raise DeskError(
            f"no verified keeping consent for narrator {narrator_id!r} — "
            "absence is not consent"
        )

    sid = _id()
    digest = body_digest(body)
    conn.execute(
        "INSERT INTO statements (id, created_at, session_id, narrator_id, taker_id,"
        " body, medium, captured_at, consent_ref, body_sha256)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)",
        (sid, _now(), session_id, narrator_id, taker_id, body, medium,
         captured_at, narrator_id, digest),
    )
    conn.commit()
    # The digest goes into the subject's hash-chained disclosure record too.
    # Inside the database it is a checksum sitting next to the thing it
    # checksums; outside it, in a chain that detects edits and truncation, it
    # is a witness. desk_db.verify_bodies compares the two.
    consent_mod.note_disclosure(
        consent_store, narrator_id, "statement_filed",
        f"session={session_id} id={sid} sha256={digest}",
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
    consent_store: Path | str | None = None,
) -> str:
    """Break one checkable assertion out of a statement.

    The span is not decoration — a claim that cannot point back at the words
    it came from is refused by the schema, not by this function.
    """
    if source_type not in SOURCE_TYPES:
        raise DeskError(f"unknown source_type: {source_type!r}")
    _require_keeping(conn, statement_id, consent_store)
    resolved = tuple(entities) if entities is not None else extract_entities(assertion)
    cid = _id()
    try:
        conn.execute(
            "INSERT INTO claims (id, statement_id, span_start, span_end, assertion,"
            " entities, occurred_at, place, state, source_type)"
            " VALUES (?,?,?,?,?,?,?,?,'filed',?)",
            (cid, statement_id, span[0], span[1], assertion,
             json.dumps(list(resolved)), occurred_at, place, source_type),
        )
        conn.executemany(
            "INSERT OR IGNORE INTO claim_entities (claim_id, entity) VALUES (?,?)",
            [(cid, e) for e in resolved],
        )
    except sqlite3.IntegrityError as exc:
        raise DeskError(str(exc)) from exc
    conn.commit()
    return cid


def _require_keeping(conn, statement_id, consent_store) -> None:
    """Refuse new work on a statement whose narrator has withdrawn.

    Keeping consent used to be checked only when filing, so after a narrator
    revoked, the desk happily kept building claims and docket entries on top
    of what they had already asked to stop being used.
    """
    if consent_store is None:
        return
    row = conn.execute(
        "SELECT narrator_id FROM statements WHERE id=?", (statement_id,)).fetchone()
    if row is None:
        raise DeskError(f"no such statement: {statement_id!r}")
    if not consent_mod.may_keep(consent_store, row["narrator_id"]):
        raise DeskError(
            f"keeping consent for {row['narrator_id']!r} is not in force — "
            "no new work on a withdrawn account"
        )


def quoted(conn: sqlite3.Connection, claim_id: str) -> str:
    """The words a claim was drawn from. The receipt behind every assertion."""
    row = conn.execute(
        "SELECT s.body, c.span_start, c.span_end FROM claims c"
        " JOIN statements s ON s.id = c.statement_id WHERE c.id = ?",
        (claim_id,),
    ).fetchone()
    if row is None:
        raise DeskError(f"no such claim: {claim_id!r}")
    start, end, body = row["span_start"], row["span_end"], row["body"]
    # Python slicing does not raise on an out-of-range span — it returns a
    # shorter string, or an empty one. A citation that is silently wrong is
    # worse than an error, so this refuses instead of slicing.
    if start < 0 or end <= start or end > len(body):
        raise DeskError(
            f"claim {claim_id!r} has a span that no longer resolves "
            f"({start}:{end} of {len(body)}) — refusing to quote"
        )
    return body[start:end]


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
    ruled_by = identity(ruled_by, field="ruled_by")
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
    ruled_by = identity(ruled_by, field="ruled_by")
    try:
        cur = conn.execute(
            "UPDATE claims SET ruled_by=?, ruled_at=?, ruling_note=?,"
            " source_type='unverifiable', state='uncheckable'"
            " WHERE id=? AND state IN ('filed','routed')",
            (ruled_by, _now(), note, claim_id),
        )
    except sqlite3.IntegrityError as exc:
        raise DeskError(str(exc)) from exc
    if cur.rowcount == 0:
        raise DeskError(
            f"claim {claim_id!r} is not in a state that can be marked uncheckable"
        )
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
    """What a human is uniquely needed for, ordered by that (spec §7).

    Classification matches the router's own precedence, and only counts rows
    the router wrote. Both were wrong before: the queue put a proposed gap
    above retrieval while the router put it below, so the two disagreed about
    the same claim; and it matched on `excerpt` alone, so an operator could
    pass `--excerpt "Uncheckable. No record of this could exist."` on the CLI
    and bury a checkable claim in the "confirm the gap and let it stand" pile.

    `unrouted` is its own bucket: a claim nobody has looked at is not the same
    as one the router examined and found nothing for.
    """
    counts = {"contradicted": 0, "gap_proposed": 0, "related": 0,
              "uncorroborated": 0, "unrouted": 0, "uncheckable": 0}
    rows = conn.execute(
        "SELECT c.id, c.state,"
        " SUM(CASE WHEN d.relation='contradicts' THEN 1 ELSE 0 END) AS against,"
        " SUM(CASE WHEN d.relation='contextualizes' THEN 1 ELSE 0 END) AS near,"
        " SUM(CASE WHEN d.found_by='router' AND d.relation='no_source_found'"
        "           AND d.excerpt = ? THEN 1 ELSE 0 END) AS gap,"
        " SUM(CASE WHEN d.found_by='router' THEN 1 ELSE 0 END) AS routed"
        " FROM claims c LEFT JOIN docket_entries d ON d.claim_id = c.id"
        " WHERE c.state IN ('filed','routed','uncheckable') GROUP BY c.id",
        (vocabulary.UNCHECKABLE,),
    )
    for row in rows:
        if row["state"] == "uncheckable":
            counts["uncheckable"] += 1          # already confirmed by a person
        elif row["against"]:
            counts["contradicted"] += 1
        elif row["gap"]:
            counts["gap_proposed"] += 1
        elif row["near"]:
            counts["related"] += 1
        elif row["routed"]:
            counts["uncorroborated"] += 1
        else:
            counts["unrouted"] += 1
    return counts
