#!/usr/bin/env python3
"""verify_ledger.py — walk the campaign ledger's hash chain and refuse on a break.

Companion to schema/01_ledger.sql's prev_hash/hash columns: a tamper-evidence
layer pattern-ported from Nestor's hash-chained ledger (nestor/ledger.py,
Apache-2.0, github.com/rudi193-cmd/Nestor, pinned v0.2.0). No Nestor code is
copied verbatim — this is the same prev-is-a-hash-of-the-previous-entry chain,
reimplemented against a SQL table instead of the JSONL file the Vander dogfood
used, in this repo's own idiom: a single stdlib-only script, the same "shell
out to python3" shape provision.sh uses for what the sqlite3 CLI cannot do.

A broken chain is a REFUSAL — nonzero exit, no partial credit — matching
nestor.ledger.verify's contract, not a lint that prints and continues.

Beyond the chain, two covenant guards (the reason this engine exists):

    --canon    refuse if any canon row (schema/02_canon.sql) is SEALED/REJECTED
               without a NAMED HUMAN in sealed_by, or is sealed by anything in
               NOT_A_PERSON. The machine may propose; it may not confirm.
    --rulings  report unsigned rulings (schema/04_rulings.sql). Signature
               cryptography is optional (Ed25519 needs `cryptography`); absent
               it, this reports signed-vs-unsigned counts rather than failing,
               so the guard degrades to 'unknown', never to a false 'all good'.

Usage:
    verify_ledger.py /path/to/box/campaign.db
    verify_ledger.py /path/to/box/campaign.db --canon --rulings
    verify_ledger.py --self-test        # prove a tampered row IS refused

Exit codes:
    0   ledger chain intact (or no campaign db yet — nothing to verify), and
        every requested extra guard passed
    1   chain broken — a row's hash does not match its stored value, or a
        prev_hash does not match the previous row's hash (tamper, or a
        row/rows removed or reordered); OR a --canon guard violation
    2   the ledger table exists but predates prev_hash/hash (an unmigrated
        box) — NOT a tamper finding, but still a refusal: this script cannot
        vouch for a chain that was never started
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
import tempfile

GENESIS = "genesis"

# terpsi-music records/sealing.py _NOT_A_PERSON — a "seal" attributed to any of
# these is not a human seal. Keep in sync with schema/02_canon.sql's header.
NOT_A_PERSON = {
    "", "system", "machine", "ai", "gm", "dm-bot", "assistant",
    "claude", "model", "auto", "none", "null",
}


def canonical_row(id_, ts, session, kind, note, state, prev_hash) -> str:
    """The exact JSON form each ledger row's `hash` is computed over.

    Key order and separators matter — this must serialize identically on
    whichever side (writer or verifier) computes it. Mirrors nestor.ledger's
    convention: json.dumps with the default (", ", ": ") separators and
    ensure_ascii=False. `state` is already-serialized JSON text and is embedded
    verbatim (as a string) so the writer and verifier agree without re-parsing.
    """
    obj = {
        "id": id_,
        "ts": ts,
        "session": session,
        "kind": kind,
        "note": note,
        "state": state,
        "prev_hash": prev_hash,
    }
    return json.dumps(obj, ensure_ascii=False)


def row_hash(*args) -> str:
    return hashlib.sha256(canonical_row(*args).encode("utf-8")).hexdigest()


def verify_chain(db_path: str) -> tuple[int, str]:
    """Walk the ledger table in id order. Returns (exit_code, detail).

    0 = intact, 1 = broken chain, 2 = unmigrated table (no prev_hash/hash).
    """
    con = sqlite3.connect(db_path)
    try:
        try:
            rows = con.execute(
                "SELECT id, ts, session, kind, note, state, prev_hash, hash "
                "FROM ledger ORDER BY id ASC"
            ).fetchall()
        except sqlite3.OperationalError as e:
            return 2, (
                f"cannot verify: {e} — this campaign.db predates the "
                f"prev_hash/hash columns in schema/01_ledger.sql. Not a tamper "
                f"finding: the chain was never started here."
            )
    finally:
        con.close()

    if not rows:
        return 0, "ledger table is empty — nothing to verify (a fresh box)"

    prev = GENESIS
    for (id_, ts, session, kind, note, state, prev_hash, stored_hash) in rows:
        if prev_hash != prev:
            return 1, (
                f"broken chain at ledger id={id_}: prev_hash={prev_hash!r} "
                f"expected {prev!r} — a row was altered, removed, or reordered"
            )
        recomputed = row_hash(id_, ts, session, kind, note, state, prev_hash)
        if recomputed != stored_hash:
            return 1, (
                f"broken chain at ledger id={id_}: stored hash {stored_hash[:16]}… "
                f"does not match recomputed {recomputed[:16]}… — this row's "
                f"content was altered after it was written"
            )
        prev = stored_hash
    return 0, f"intact — {len(rows)} ledger entries"


def verify_canon(db_path: str) -> tuple[int, str]:
    """The covenant guard: no machine-sealed canon. Returns (exit_code, detail).

    A SEALED or REJECTED canon row must name a real human in sealed_by. A seal
    by anything in NOT_A_PERSON is refused — 'the human seals canon' is the
    thesis, and a seal the machine could have written is no seal.
    """
    con = sqlite3.connect(db_path)
    try:
        try:
            rows = con.execute(
                "SELECT id, fact, status, sealed_by FROM canon "
                "WHERE status IN ('SEALED','REJECTED')"
            ).fetchall()
        except sqlite3.OperationalError:
            return 0, "no canon table yet — nothing to check"
    finally:
        con.close()
    for (id_, fact, status, sealed_by) in rows:
        who = (sealed_by or "").strip().lower()
        if who in NOT_A_PERSON:
            return 1, (
                f"canon id={id_} is {status} but sealed_by={sealed_by!r} is not "
                f"a person — the machine may propose, it may not confirm. "
                f"fact: {fact[:60]!r}"
            )
    return 0, f"canon guard passed — {len(rows)} sealed/rejected rows, all human-attributed"


def report_rulings(db_path: str) -> tuple[int, str]:
    """Report signed vs unsigned rulings. Degrades to a count, never a false OK.

    Signature *cryptography* (Ed25519) is optional and box-side; this reporter
    does not fail on unsigned house-notes — it surfaces them so a reader knows
    what carries proof and what is just a note. Absence is reported as a value,
    not swallowed.
    """
    con = sqlite3.connect(db_path)
    try:
        try:
            rows = con.execute(
                "SELECT COUNT(*), SUM(CASE WHEN sig IS NOT NULL AND sig <> '' "
                "THEN 1 ELSE 0 END) FROM rulings WHERE invalid_at IS NULL"
            ).fetchone()
        except sqlite3.OperationalError:
            return 0, "no rulings table yet — nothing to report"
    finally:
        con.close()
    total = rows[0] or 0
    signed = rows[1] or 0
    return 0, f"rulings: {signed}/{total} active rulings carry a signature ({total - signed} unsigned house-notes)"


# ── self-test: build a clean chain, verify, tamper a row, confirm refusal ─────
def _self_test() -> int:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        con = sqlite3.connect(path)
        con.executescript(
            open(os.path.join(os.path.dirname(__file__), "..", "schema",
                              "01_ledger.sql")).read()
        )
        # write three chained rows the way a correct writer would
        prev = GENESIS
        for i in range(1, 4):
            ts = f"2026-08-13T00:0{i}:00"
            note = f"turn {i}"
            state = json.dumps({"round": i}, ensure_ascii=False)
            h = row_hash(i, ts, 1, "turn", note, state, prev)
            con.execute(
                "INSERT INTO ledger (id, ts, session, kind, note, state, prev_hash, hash) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (i, ts, 1, "turn", note, state, prev, h),
            )
            prev = h
        con.commit()
        con.close()

        code, detail = verify_chain(path)
        print(f"  clean chain: exit {code} — {detail}")
        if code != 0:
            print("  !! self-test FAILED: a clean chain should verify")
            return 1

        # tamper: rewrite row 2's note without recomputing hashes
        con = sqlite3.connect(path)
        con.execute("UPDATE ledger SET note='TAMPERED' WHERE id=2")
        con.commit()
        con.close()
        code, detail = verify_chain(path)
        print(f"  tampered row: exit {code} — {detail}")
        if code != 1:
            print("  !! self-test FAILED: a tampered row MUST be refused (exit 1)")
            return 1
        print("  self-test PASSED: clean chain verifies, tampered row refused.")
        return 0
    finally:
        os.unlink(path)


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:]]
    if "--self-test" in args:
        return _self_test()
    paths = [a for a in args if not a.startswith("--")]
    if not paths:
        print(__doc__.strip().splitlines()[0])
        print("usage: verify_ledger.py /path/to/box/campaign.db [--canon] [--rulings]")
        return 0
    db_path = paths[0]
    if not os.path.exists(db_path):
        print(f"  no campaign db at {db_path} — nothing to verify (a fresh box)")
        return 0

    code, detail = verify_chain(db_path)
    print(f"  ledger chain: {detail}")
    worst = code

    if "--canon" in args:
        c, d = verify_canon(db_path)
        print(f"  canon guard:  {d}")
        worst = max(worst, c)
    if "--rulings" in args:
        _, d = report_rulings(db_path)
        print(f"  {d}")

    if worst == 0:
        print("  OK — the book is honest.")
    return worst


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
