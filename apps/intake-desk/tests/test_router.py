"""The router.

The first test in this file is the vocabulary test, and it is the point: a
confident wrong answer about somebody's grandfather ends the product, so the
router's language is held before anything about its retrieval is checked.
"""
from __future__ import annotations

import pytest

import consent as consent_mod
import desk
import desk_db
import router

TAKER = "penny"
WITNESS = "wrench"


@pytest.fixture()
def vault(tmp_path):
    store = tmp_path / "consent"
    for narrator in ("slappy", "the-colonel", "wrench"):
        consent_mod.grant_keeping(store, narrator, granted_by="operator")
    return desk_db.connect(tmp_path / "desk.sqlite3"), store


def _claim(conn, store, narrator, body, assertion, occurred_at=None, span=None):
    sid = desk.file_statement(
        conn, consent_store=store, session_id="s1", narrator_id=narrator,
        taker_id=TAKER, body=body,
    )
    return desk.add_claim(
        conn, statement_id=sid, span=span or (0, len(body)),
        assertion=assertion, occurred_at=occurred_at,
    )


# ── the refusal contract ──────────────────────────────────────────────────────

def test_a_name_is_not_a_verdict():
    """Whole words only — a narrator called Charlie must not trip the gate."""
    assert router.verdict_language("Charlie rode with Trueman.") is None
    assert router.verdict_language("This is verified.") == "verified"


def test_the_router_has_exactly_five_sentences():
    """Its whole vocabulary of conclusion. Nothing stronger exists."""
    assert router.CORROBORATED == "Corroborated by {n} sources."
    assert router.CONTRADICTED == "Contradicted. {a}; {b}."
    assert router.NO_SOURCE == "No source found. This is checkable — nobody has checked it."
    assert router.UNCHECKABLE == "Uncheckable. No record of this could exist."
    assert router.UNCORROBORATED == "Uncorroborated. Only the narrator asserts this."


@pytest.mark.parametrize("template", [
    router.CORROBORATED, router.CONTRADICTED, router.NO_SOURCE,
    router.UNCHECKABLE, router.UNCORROBORATED,
])
def test_no_verdict_language_in_the_contract(template):
    found = router.verdict_language(template)
    assert found is None, f"{found!r} is a verdict, not evidence"


def test_no_verdict_language_in_anything_the_router_emits(vault):
    """Over real output, not just the constants."""
    conn, store = vault
    a = _claim(conn, store, "slappy", "We rode to Laconia in 1998.",
               "They rode to Laconia.", occurred_at="1998")
    b = _claim(conn, store, "the-colonel", "Laconia was 2001, not 1998.",
               "They rode to Laconia.", occurred_at="2001")
    c = _claim(conn, store, "slappy", "I never told anybody how scared I was.",
               "The narrator was frightened.")
    d = _claim(conn, store, "slappy", "Miller's Bar had a back room.",
               "Miller's Bar had a back room.")

    emitted = []
    for cid in (a, b, c, d):
        finding = router.route(conn, cid)
        emitted.append(finding.sentence())
    for row in conn.execute("SELECT excerpt FROM docket_entries"):
        emitted.append(row["excerpt"] or "")

    found = router.verdict_language(" ".join(emitted))
    assert found is None, f"router emitted {found!r}"


# ── it never rules ────────────────────────────────────────────────────────────

def test_routing_never_sets_a_ruler_or_a_confidence(vault):
    conn, store = vault
    cid = _claim(conn, store, "slappy", "Miller's Bar closed.", "Miller's Bar closed.")
    before = conn.execute("SELECT confidence FROM claims WHERE id=?", (cid,)).fetchone()["confidence"]
    router.route(conn, cid)
    row = conn.execute("SELECT * FROM claims WHERE id=?", (cid,)).fetchone()
    assert row["ruled_by"] is None
    assert row["ruled_at"] is None
    assert row["confidence"] == before
    assert row["state"] == "routed"


def test_the_router_cannot_reach_a_terminal_state(vault):
    """`uncheckable` is proposed here and confirmed by a person."""
    conn, store = vault
    cid = _claim(conn, store, "slappy", "I never told anybody how scared I was.",
                 "The narrator was frightened.")
    finding = router.route(conn, cid)
    assert finding.status == "uncheckable_proposed"
    state = conn.execute("SELECT state FROM claims WHERE id=?", (cid,)).fetchone()["state"]
    assert state == "routed", "only a human moves a claim to uncheckable"

    desk.mark_uncheckable(conn, claim_id=cid, ruled_by=WITNESS, note="confirmed")
    assert conn.execute(
        "SELECT state FROM claims WHERE id=?", (cid,)).fetchone()["state"] == "uncheckable"


# ── 1. resolve ────────────────────────────────────────────────────────────────

def test_entities_are_proper_nouns_and_years():
    found = router.extract_entities("They rode to Laconia with Slappy in 1998.")
    assert "Laconia" in found and "Slappy" in found and "1998" in found


def test_sentence_initial_common_words_are_not_entities():
    found = router.extract_entities("The shop closed. Nobody said it out loud.")
    assert "The" not in found and "Nobody" not in found
    assert "The shop" not in found


# ── 2. corroborate ────────────────────────────────────────────────────────────

def test_a_second_narrator_corroborates(vault):
    conn, store = vault
    _claim(conn, store, "the-colonel", "Miller's Bar had a back room.",
           "Miller's Bar had a back room.")
    cid = _claim(conn, store, "slappy", "Miller's Bar had a back room.",
                 "Miller's Bar had a back room.")
    finding = router.route(conn, cid)
    assert finding.status == "corroborated"
    assert finding.sentence() == "Corroborated by 2 sources."


def test_the_same_narrator_twice_is_not_corroboration(vault):
    """Independence is the whole point — one source saying it twice is one source."""
    conn, store = vault
    _claim(conn, store, "slappy", "Miller's Bar had a back room.",
           "Miller's Bar had a back room.")
    cid = _claim(conn, store, "slappy", "Miller's Bar definitely had a back room.",
                 "Miller's Bar had a back room.")
    finding = router.route(conn, cid)
    assert finding.status == "uncorroborated"
    assert finding.sentence() == "Uncorroborated. Only the narrator asserts this."


def test_disagreeing_dates_contradict_and_the_router_does_not_pick(vault):
    conn, store = vault
    _claim(conn, store, "the-colonel", "Laconia was 2001.", "They rode to Laconia.",
           occurred_at="2001")
    cid = _claim(conn, store, "slappy", "We rode to Laconia in 1998.",
                 "They rode to Laconia.", occurred_at="1998")
    finding = router.route(conn, cid)
    assert finding.status == "contradicted"
    said = finding.sentence()
    assert said.startswith("Contradicted.")
    assert "1998" in said and "2001" in said, "both accounts survive, neither is chosen"


def test_nothing_related_is_a_checkable_gap_not_a_verdict(vault):
    conn, store = vault
    cid = _claim(conn, store, "slappy", "Miller's Bar had a back room.",
                 "Miller's Bar had a back room.")
    finding = router.route(conn, cid)
    assert finding.status == "no_source_found"
    assert finding.sentence() == (
        "No source found. This is checkable — nobody has checked it."
    )


# ── 3. sequence ───────────────────────────────────────────────────────────────

def test_fuzzy_dates_still_sequence(vault):
    conn, store = vault
    _claim(conn, store, "the-colonel", "Laconia, summer 1998.", "They rode to Laconia.",
           occurred_at="summer 1998")
    cid = _claim(conn, store, "slappy", "Laconia in 1998-06 or so.",
                 "They rode to Laconia.", occurred_at="1998-06?")
    finding = router.route(conn, cid)
    assert finding.status == "corroborated", "same year, fuzzily stated, is not a conflict"
    assert finding.timeline and finding.timeline[0][1] == 1998


def test_a_claim_with_no_date_is_not_a_date_conflict(vault):
    conn, store = vault
    _claim(conn, store, "the-colonel", "Laconia was 2001.", "They rode to Laconia.",
           occurred_at="2001")
    cid = _claim(conn, store, "slappy", "We rode to Laconia.", "They rode to Laconia.")
    assert router.route(conn, cid).status == "corroborated"


# ── 4. the gap ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text", [
    "I never told anybody how scared I was.",
    "Nobody knew what he was thinking.",
    "I felt like the whole thing was over.",
    "She was ashamed about it for years.",
])
def test_interior_state_is_proposed_as_uncheckable(text):
    assert router.proposes_uncheckable(text)


@pytest.mark.parametrize("text", [
    "We pushed it four miles to the campground.",
    "Miller's Bar closed in 1998.",
])
def test_ordinary_checkable_claims_are_not(text):
    assert not router.proposes_uncheckable(text)


# ── the docket ────────────────────────────────────────────────────────────────

def test_the_docket_names_its_source(vault):
    conn, store = vault
    other = _claim(conn, store, "the-colonel", "Miller's Bar had a back room.",
                   "Miller's Bar had a back room.")
    cid = _claim(conn, store, "slappy", "Miller's Bar had a back room.",
                 "Miller's Bar had a back room.")
    router.route(conn, cid)
    entries = desk.docket(conn, cid)
    assert entries and entries[0]["relation"] == "corroborates"
    assert entries[0]["source_ref"] == f"claim:{other}"
    assert entries[0]["found_by"] == "router"


def test_route_all_sweeps_only_unrouted_claims(vault):
    conn, store = vault
    _claim(conn, store, "slappy", "Miller's Bar closed.", "Miller's Bar closed.")
    _claim(conn, store, "slappy", "The Farm flooded.", "The Farm flooded.")
    assert len(router.route_all(conn)) == 2
    assert router.route_all(conn) == [], "already routed, nothing to sweep"


def test_withheld_claims_are_not_used_as_evidence(vault):
    conn, store = vault
    other = _claim(conn, store, "the-colonel", "Miller's Bar had a back room.",
                   "Miller's Bar had a back room.")
    desk.withhold(conn, claim_id=other, reason="narrator asked")
    cid = _claim(conn, store, "slappy", "Miller's Bar had a back room.",
                 "Miller's Bar had a back room.")
    assert router.route(conn, cid).status == "no_source_found"


# ── the queue distinguishes a proposed gap from an unchecked one ──────────────

def test_a_proposed_gap_is_its_own_queue_bucket(vault):
    """Confirming a gap is real is different work from finding an unlooked-for
    source, so it must not hide inside `uncorroborated`."""
    conn, store = vault
    _claim(conn, store, "slappy", "I never told anybody how scared I was.",
           "The narrator was frightened.")
    _claim(conn, store, "slappy", "The Farm flooded.", "The Farm flooded.")
    router.route_all(conn)
    counts = desk.queue(conn)
    assert counts["gap_proposed"] == 1
    assert counts["uncorroborated"] == 1
    assert counts["uncheckable"] == 0, "not until a person confirms it"


def test_confirming_the_gap_moves_it_out_of_the_proposed_bucket(vault):
    conn, store = vault
    cid = _claim(conn, store, "slappy", "I never told anybody how scared I was.",
                 "The narrator was frightened.")
    router.route(conn, cid)
    desk.mark_uncheckable(conn, claim_id=cid, ruled_by=WITNESS, note="confirmed")
    counts = desk.queue(conn)
    assert counts["gap_proposed"] == 0 and counts["uncheckable"] == 1
