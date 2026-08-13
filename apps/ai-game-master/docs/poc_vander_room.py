#!/usr/bin/env python3
"""poc_vander_room.py — the Vander boss room, replayed through the real schema.

An EXHIBIT, not the product: it proves the blueprint's four schemas actually
carry a game — the same beats the Vander dogfood sealed over a JSONL file
(vander_tracker.py), now over campaign.db. It provisions a throwaway box in a
temp dir, runs the boss-room beats, and verifies the chain at the end.

What it demonstrates, in order:
  1. a RULING is proposed and signed  — "the button is bait; restraint wins"
  2. a GUEST is drafted then SEALED    — Bill Cipher, welcomed by a NAMED DM
  3. a canon FACT is sealed            — Prince Villippe is freed
  4. every beat snapshots to the hash-chained LEDGER
  5. the chain + the --canon guard verify at the end

The DM's name here is a placeholder ('DM-Sean') standing in for the real human
the product requires at seal time. In production nothing but an actual person's
confirmation writes a SEALED row — this exhibit passes a name through the same
API to show the mechanism, exactly as a test does. No machine seals canon.
"""
from __future__ import annotations
import hashlib
import json
import os
import subprocess
import sqlite3
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DM = "DM-Sean"                      # a NAMED human stands here (placeholder for the exhibit)
TS = "2026-08-13T20:00:00"         # fixed so the exhibit is reproducible


def canonical_row(id_, ts, session, kind, note, state, prev_hash) -> str:
    return json.dumps(
        {"id": id_, "ts": ts, "session": session, "kind": kind,
         "note": note, "state": state, "prev_hash": prev_hash},
        ensure_ascii=False,
    )


def append_turn(con, session, kind, note, state_obj):
    """Write one chained ledger turn — prev_hash = the previous row's hash."""
    row = con.execute("SELECT hash FROM ledger ORDER BY id DESC LIMIT 1").fetchone()
    prev = row[0] if row else "genesis"
    state = json.dumps(state_obj, ensure_ascii=False)
    cur = con.execute(
        "INSERT INTO ledger (ts, session, kind, note, state, prev_hash, hash) "
        "VALUES (?,?,?,?,?,?,?)",
        (TS, session, kind, note, state, prev, ""),
    )
    id_ = cur.lastrowid
    h = hashlib.sha256(
        canonical_row(id_, TS, session, kind, note, state, prev).encode("utf-8")
    ).hexdigest()
    con.execute("UPDATE ledger SET hash=? WHERE id=?", (h, id_))
    con.commit()
    return id_


def main() -> int:
    box = tempfile.mkdtemp(prefix="vander-poc-")
    db = os.path.join(box, "campaign.db")
    # provision (reuse the real bootstrap so the exhibit can't drift from it)
    subprocess.run(["bash", os.path.join(ROOT, "bootstrap", "provision.sh"), box],
                   check=True, capture_output=True)
    con = sqlite3.connect(db)

    print("="*68)
    print("  THE VANDER BOSS ROOM — replayed through campaign.db")
    print("="*68)

    # session opens
    lid = append_turn(con, 1, "session_open",
                      "The door grinds open on the red-button room.",
                      {"scene": "red-button room", "party": ["Grask", "Wren", "Vex"]})

    # 1) a RULING — the DM's house call, signed (HMAC here; Ed25519 in the box)
    ruling = "The button is bait. Restraint is the win — never press it; survive the timer."
    sig = hashlib.sha256((ruling + "::" + DM).encode()).hexdigest()  # stand-in signature
    con.execute(
        "INSERT INTO rulings (ts, text, scope, signer, sig, sig_scheme, ledger_id) "
        "VALUES (?,?,?,?,?,?,?)",
        (TS, ruling, "canon", DM, sig, "hmac-sha256", lid),
    )
    con.commit()
    print(f"\n  RULING (signed by {DM}): {ruling}")

    # 2) a GUEST — a player proposes Bill Cipher; the DM seals him into canon
    con.execute(
        "INSERT INTO entities (kind, canonical, aliases, sheet, sealed_by, introduced_ledger_id) "
        "VALUES ('guest','Bill Cipher',?,?,?,?)",
        (json.dumps(["the triangle", "Cipher"]),
         json.dumps({"origin": "Gravity Falls", "brought_by": "a player"}),
         DM, lid),
    )
    lid = append_turn(con, 1, "turn",
                      "A player walks Bill Cipher into the valley; the DM says yes-and.",
                      {"guest": "Bill Cipher", "brought_by": "a player at the table"})
    con.execute(
        "INSERT INTO canon (ts, fact, status, proposed_by, sealed_by, sealed_at, ledger_id, reason) "
        "VALUES (?,?, 'SEALED', 'a player', ?, ?, ?, ?)",
        (TS, "Bill Cipher is a sealed guest of the Vander valley.", DM, TS, lid,
         "rule-of-cool; the table invented him and the DM welcomed him in."),
    )
    con.commit()
    print(f"  GUEST sealed by {DM}: Bill Cipher — 'guest, sealed by {DM}, session 1' (un-retconnable)")

    # 3) the climax fact — sealed by the human, snapshotted to the chain
    lid = append_turn(con, 1, "turn",
                      "Restraint held; the tomes calmed the Kin Spirit; the chains fell.",
                      {"boss": "cleared by restraint + knowledge, not the button"})
    con.execute(
        "INSERT INTO canon (ts, fact, status, proposed_by, sealed_by, sealed_at, ledger_id, reason) "
        "VALUES (?,?, 'SEALED', 'the machine (proposed)', ?, ?, ?, ?)",
        (TS, "Prince Villippe is freed.", DM, TS, lid, "the party freed him; the DM sealed it."),
    )
    append_turn(con, 1, "session_close", "Session closed — the Prince is freed.",
                {"result": "victory by restraint"})
    con.commit()
    print(f"  CANON sealed by {DM}: Prince Villippe is freed.")

    # a PENDING the machine proposed but NO ONE sealed — stays a proposal
    con.execute(
        "INSERT INTO canon (ts, fact, status, proposed_by) "
        "VALUES (?,?, 'PENDING', 'the machine')",
        (TS, "The Silver Compass points to the next kingdom (sequel hook).",)
    )
    con.commit()
    print("  PENDING (machine-proposed, unsealed): the Silver Compass hook — waits for a human.")

    con.close()

    # verify: the chain and the covenant guard
    print("\n" + "-"*68)
    r = subprocess.run(
        [sys.executable, os.path.join(ROOT, "bootstrap", "verify_ledger.py"),
         db, "--canon", "--rulings"],
        capture_output=True, text=True,
    )
    print(r.stdout.strip())
    # clean up the throwaway box (it is DATA; it never persists)
    for f in os.listdir(box):
        fp = os.path.join(box, f)
        if os.path.isfile(fp):
            os.unlink(fp)
    for d in ("corpus", "keys"):
        dp = os.path.join(box, d)
        if os.path.isdir(dp):
            os.rmdir(dp)
    os.rmdir(box)
    if r.returncode != 0:
        print("  !! EXHIBIT FAILED: the chain or the canon guard refused")
        return 1
    print("\n  EXHIBIT OK — the schema carried the game, the human sealed canon,")
    print("  and the book verifies. The box was a throwaway; nothing persisted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
