"""The four invariants of spec §4, and the two transitions that guard §3.

These are the app. The router, the model, the UI are assistance; this is the
discipline, and it is enforced in the schema so it holds for anything that
opens the file — not only for code that goes through desk.py.
"""
from __future__ import annotations

import sqlite3

import pytest

import consent as consent_mod
import desk
import desk_db

NARRATOR = "slappy"
TAKER = "penny"
WITNESS = "wrench"

BODY = "The shop closed the summer after Laconia. Nobody wanted to say it out loud."


@pytest.fixture()
def vault(tmp_path):
    store = tmp_path / "consent"
    consent_mod.grant_keeping(store, NARRATOR, granted_by="operator")
    conn = desk_db.connect(tmp_path / "desk.sqlite3")
    sid = desk.file_statement(
        conn, consent_store=store, session_id="s1", narrator_id=NARRATOR,
        taker_id=TAKER, body=BODY, medium="transcript",
    )
    return conn, store, sid


# ── 1. the verbatim account is write-once ─────────────────────────────────────

def test_body_cannot_be_edited(vault):
    conn, store, sid = vault
    with pytest.raises(sqlite3.IntegrityError, match="write-once"):
        conn.execute("UPDATE statements SET body='something else' WHERE id=?", (sid,))


def test_narrator_and_taker_cannot_be_reassigned(vault):
    conn, store, sid = vault
    with pytest.raises(sqlite3.IntegrityError, match="write-once"):
        conn.execute("UPDATE statements SET narrator_id='someone' WHERE id=?", (sid,))


def test_a_careless_rewrite_is_detectable(vault):
    conn, store, sid = vault
    assert desk_db.verify_bodies(conn) == []
    conn.execute("DROP TRIGGER statements_write_once")
    conn.execute("UPDATE statements SET body='rewritten' WHERE id=?", (sid,))
    assert desk_db.verify_bodies(conn) == [sid]


def test_a_careful_rewrite_is_only_caught_by_the_external_chain(vault):
    """The in-row digest is a checksum, not a witness.

    Body and digest live in the same row, so anything that can rewrite one can
    rewrite the other and leave the row self-consistent. Only the disclosure
    chain — hash-linked, anchored, outside this file — disagrees.
    """
    conn, store, sid = vault
    conn.execute("DROP TRIGGER statements_write_once")
    conn.execute("UPDATE statements SET body=?, body_sha256=? WHERE id=?",
                 ("rewritten", desk_db.body_digest("rewritten"), sid))
    assert desk_db.verify_bodies(conn) == [], "self-consistent: the row cannot tell"
    assert desk_db.verify_bodies(conn, store) == [sid], "the chain can"


# ── 2. nothing is deleted ─────────────────────────────────────────────────────

def test_statements_are_never_deleted(vault):
    conn, store, sid = vault
    with pytest.raises(sqlite3.IntegrityError, match="never deleted"):
        conn.execute("DELETE FROM statements WHERE id=?", (sid,))


def test_claims_are_never_deleted(vault):
    conn, store, sid = vault
    cid = desk.add_claim(conn, consent_store=store, statement_id=sid, span=(0, 40), assertion="The shop closed.")
    with pytest.raises(sqlite3.IntegrityError, match="never deleted"):
        conn.execute("DELETE FROM claims WHERE id=?", (cid,))


def test_withhold_keeps_the_record(vault):
    conn, store, sid = vault
    cid = desk.add_claim(conn, consent_store=store, statement_id=sid, span=(0, 40), assertion="The shop closed.")
    desk.withhold(conn, claim_id=cid, reason="narrator asked")
    row = conn.execute("SELECT state, corrections FROM claims WHERE id=?", (cid,)).fetchone()
    assert row["state"] == "withheld"
    assert "narrator asked" in row["corrections"]


# ── 3. a claim must point back at the words it came from ──────────────────────

def test_span_beyond_the_body_is_refused(vault):
    conn, store, sid = vault
    with pytest.raises(desk.DeskError, match="does not resolve"):
        desk.add_claim(conn, consent_store=store, statement_id=sid, span=(0, len(BODY) + 1), assertion="x")


def test_inverted_span_is_refused(vault):
    conn, store, sid = vault
    with pytest.raises(desk.DeskError, match="does not resolve"):
        desk.add_claim(conn, consent_store=store, statement_id=sid, span=(30, 10), assertion="x")


def test_quoted_returns_the_source_words(vault):
    conn, store, sid = vault
    cid = desk.add_claim(conn, consent_store=store, statement_id=sid, span=(0, 15), assertion="The shop closed.")
    assert desk.quoted(conn, cid) == BODY[0:15]


# ── 4. verified_by != author (§0.2). The gate with no override. ───────────────

def test_narrator_cannot_rule_their_own_claim(vault):
    conn, store, sid = vault
    cid = desk.add_claim(conn, consent_store=store, statement_id=sid, span=(0, 40), assertion="The shop closed.")
    with pytest.raises(desk.DeskError, match="neither the narrator nor the taker"):
        desk.rule(conn, claim_id=cid, ruled_by=NARRATOR, confidence="high")


def test_taker_cannot_rule_the_claim_they_took(vault):
    conn, store, sid = vault
    cid = desk.add_claim(conn, consent_store=store, statement_id=sid, span=(0, 40), assertion="The shop closed.")
    with pytest.raises(desk.DeskError, match="neither the narrator nor the taker"):
        desk.rule(conn, claim_id=cid, ruled_by=TAKER, confidence="high")


def test_a_third_hand_can_rule(vault):
    conn, store, sid = vault
    cid = desk.add_claim(conn, consent_store=store, statement_id=sid, span=(0, 40), assertion="The shop closed.")
    desk.rule(conn, claim_id=cid, ruled_by=WITNESS, confidence="medium", note="two sources")
    row = conn.execute("SELECT * FROM claims WHERE id=?", (cid,)).fetchone()
    assert row["state"] == "ruled" and row["ruled_by"] == WITNESS


def test_the_gate_holds_against_a_raw_writer(vault):
    """Not only desk.rule() — any writer that opens the file."""
    conn, store, sid = vault
    cid = desk.add_claim(conn, consent_store=store, statement_id=sid, span=(0, 40), assertion="The shop closed.")
    with pytest.raises(sqlite3.IntegrityError, match="neither the narrator nor the taker"):
        conn.execute("UPDATE claims SET ruled_by=? WHERE id=?", (TAKER, cid))


# ── transitions ───────────────────────────────────────────────────────────────

def test_publishing_an_unruled_claim_is_refused(vault):
    conn, store, sid = vault
    cid = desk.add_claim(conn, consent_store=store, statement_id=sid, span=(0, 40), assertion="The shop closed.")
    with pytest.raises(desk.DeskError, match="not ruled"):
        desk.publish(conn, claim_id=cid)


def test_publish_is_refused_by_the_schema_too(vault):
    conn, store, sid = vault
    cid = desk.add_claim(conn, consent_store=store, statement_id=sid, span=(0, 40), assertion="The shop closed.")
    with pytest.raises(sqlite3.IntegrityError, match="before it is ruled"):
        conn.execute("UPDATE claims SET state='published' WHERE id=?", (cid,))


def test_uncheckable_is_a_successful_outcome(vault):
    conn, store, sid = vault
    cid = desk.add_claim(
        conn, consent_store=store, statement_id=sid, span=(41, len(BODY)),
        assertion="Nobody wanted to say it out loud.",
    )
    desk.mark_uncheckable(conn, claim_id=cid, ruled_by=WITNESS, note="no source could exist")
    row = conn.execute("SELECT * FROM claims WHERE id=?", (cid,)).fetchone()
    assert row["state"] == "uncheckable"
    assert row["source_type"] == "unverifiable"
    assert row["ruled_by"] == WITNESS


def test_docket_entry_moves_a_claim_to_routed(vault):
    conn, store, sid = vault
    cid = desk.add_claim(conn, consent_store=store, statement_id=sid, span=(0, 40), assertion="The shop closed.")
    desk.add_docket_entry(
        conn, claim_id=cid, relation="contradicts", source_kind="vault",
        found_by="router", source_ref="claim:other", excerpt="closed in the spring",
    )
    assert conn.execute("SELECT state FROM claims WHERE id=?", (cid,)).fetchone()["state"] == "routed"


def test_queue_puts_contradictions_where_a_human_is_needed(vault):
    conn, store, sid = vault
    a = desk.add_claim(conn, consent_store=store, statement_id=sid, span=(0, 20), assertion="a")
    b = desk.add_claim(conn, consent_store=store, statement_id=sid, span=(20, 40), assertion="b")
    desk.add_docket_entry(conn, claim_id=a, relation="contradicts",
                          source_kind="vault", found_by="router")
    counts = desk.queue(conn)
    assert counts["contradicted"] == 1
    assert counts["unrouted"] == 1, "a claim nobody looked at is not a finding"
    assert b
