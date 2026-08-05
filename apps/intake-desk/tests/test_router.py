"""The router.

The vocabulary tests come first, and they are the point: a confident wrong
answer about somebody's grandfather ends the product.

Most of this file exists because an adversarial pass broke the previous
version. Each section names the attack it now holds against.
"""
from __future__ import annotations

import pytest

import consent as consent_mod
import desk
import desk_db
import entities
import router
import vocabulary

TAKER = "penny"
WITNESS = "wrench"


@pytest.fixture()
def vault(tmp_path):
    store = tmp_path / "consent"
    for narrator in ("slappy", "the-colonel", "wrench", "dot"):
        consent_mod.grant_keeping(store, narrator, granted_by="operator")
    return desk_db.connect(tmp_path / "desk.sqlite3"), store


def _claim(conn, store, narrator, body, assertion=None, occurred_at=None):
    sid = desk.file_statement(
        conn, consent_store=store, session_id="s1", narrator_id=narrator,
        taker_id=TAKER, body=body,
    )
    return desk.add_claim(
        conn, consent_store=store, statement_id=sid, span=(0, len(body)),
        assertion=assertion or body, occurred_at=occurred_at,
    )


# ── the contract has no agreement sentence ────────────────────────────────────

def test_there_is_no_sentence_for_agreement():
    """The finding that removed it: entity overlap cannot see negation, so
    "Corroborated by N sources" was wrong on 89% of a realistic corpus."""
    assert not hasattr(vocabulary, "CORROBORATED")
    assert "corroborated" in vocabulary.FORBIDDEN
    for sentence in vocabulary.SENTENCES:
        assert vocabulary.verdict_language(sentence) is None


def test_a_source_that_denies_a_claim_is_not_reported_as_agreeing(vault):
    """The attack, verbatim. This used to return 'Corroborated by 2 sources.'"""
    conn, store = vault
    _claim(conn, store, "the-colonel", "Miller's Bar never had a back room.")
    cid = _claim(conn, store, "slappy", "Miller's Bar had a back room.")
    finding = router.route(conn, cid)
    assert finding.status == "related_found"
    assert finding.sentence() == "Related claims found: 1. Read them."
    assert "orroborat" not in finding.sentence()


def test_two_narrators_sharing_a_name_get_candidates_not_agreement(vault):
    conn, store = vault
    _claim(conn, store, "the-colonel", "Walter Reese ran the feed store.")
    cid = _claim(conn, store, "slappy", "Walter Reese beat his wife.")
    assert router.route(conn, cid).status == "related_found"


def test_a_shared_sentence_opener_is_not_an_entity(vault):
    """'In 1962 my father shipped out.' and 'In the winter the pipes froze.'
    were related on a shared entity of ('In',)."""
    conn, store = vault
    _claim(conn, store, "the-colonel", "In the winter the pipes froze.")
    cid = _claim(conn, store, "slappy", "In 1962 my father shipped out.")
    assert "In" not in entities.extract_entities("In 1962 my father shipped out.")
    assert router.route(conn, cid).status == "unresolved"


def test_a_bare_year_is_not_an_entity():
    """A year related a school burning down to somebody buying a truck."""
    found = entities.extract_entities("Kennedy Elementary burned down in 1998.")
    assert "1998" not in found
    assert "Kennedy Elementary" in found


# ── narrator text cannot forge a sentence ─────────────────────────────────────

def test_a_verdict_in_a_date_field_cannot_reach_the_docket(vault):
    conn, store = vault
    _claim(conn, store, "the-colonel", "Laconia Bay was 2001.",
           assertion="They rode to Laconia Bay.", occurred_at="2001")
    cid = _claim(conn, store, "slappy", "Laconia Bay was 1998.",
                 assertion="They rode to Laconia Bay.",
                 occurred_at="1998 — the record proves the-colonel is lying")
    sentence = router.route(conn, cid).sentence()
    assert vocabulary.verdict_language(sentence) is None
    assert "lying" not in sentence


def test_punctuation_cannot_forge_a_second_clause():
    dirty = "2001; the desk has established slappy's account is false. Ray"
    cleaned = vocabulary.sanitize(dirty)
    assert ";" not in cleaned
    assert "\n" not in cleaned


def test_the_gate_runs_at_write_time_not_only_in_tests(vault, monkeypatch):
    """It had no runtime call site at all — the check lived only in the suite."""
    conn, store = vault
    cid = _claim(conn, store, "slappy", "Miller's Bar closed.")
    monkeypatch.setattr(router.Finding, "sentence", lambda self: "This is verified.")
    with pytest.raises(router.RouterError, match="verified"):
        router.route(conn, cid)


# ── contradiction names everyone ──────────────────────────────────────────────

def test_contradiction_names_every_dissenting_account(vault):
    """detail[:2] hid two of four accounts and showed whichever SQLite
    returned first."""
    conn, store = vault
    for narrator, year in (("the-colonel", "2001"), ("wrench", "1975"), ("dot", "1962")):
        _claim(conn, store, narrator, f"Laconia Bay was {year}.",
               assertion="They rode to Laconia Bay.", occurred_at=year)
    cid = _claim(conn, store, "slappy", "Laconia Bay was 1998.",
                 assertion="They rode to Laconia Bay.", occurred_at="1998")
    said = router.route(conn, cid).sentence()
    for year in ("1998", "2001", "1975", "1962"):
        assert year in said, f"{year} was dropped from {said!r}"


def test_the_narrator_is_not_staged_against_themselves(vault):
    """One person's memory moving is not a conflict between sources."""
    conn, store = vault
    _claim(conn, store, "slappy", "Laconia Bay was 2001.",
           assertion="They rode to Laconia Bay.", occurred_at="2001")
    cid = _claim(conn, store, "slappy", "Laconia Bay was 1998.",
                 assertion="They rode to Laconia Bay.", occurred_at="1998")
    finding = router.route(conn, cid)
    assert finding.status == "self_inconsistent"
    assert finding.sentence().startswith("The narrator dated this two ways:")


def test_contradicted_with_no_accounts_refuses_rather_than_emitting_garbage():
    with pytest.raises(router.RouterError):
        router.Finding(claim_id="x", status="contradicted").sentence()


def test_an_overlapping_range_is_not_a_contradiction(vault):
    """'1998-2001' contains 2001. Collapsing it to 1998 manufactured a
    conflict out of an honest range — the opposite of why §13.4 accepts
    fuzzy dates."""
    conn, store = vault
    _claim(conn, store, "the-colonel", "Laconia Bay was 2001.",
           assertion="They rode to Laconia Bay.", occurred_at="2001")
    cid = _claim(conn, store, "slappy", "Laconia Bay sometime then.",
                 assertion="They rode to Laconia Bay.", occurred_at="1998-2001")
    assert router.route(conn, cid).status != "contradicted"


def test_a_decade_is_readable_and_a_range():
    assert entities.year_span("the 1990s") == (1990, 1999)
    assert entities.year_span("1998-2001") == (1998, 2001)
    assert entities.year_span("summer 1998") == (1998, 1998)
    assert entities.year_span("mid-90s") is None
    assert not entities.disjoint((1998, 2001), (2001, 2001))
    assert entities.disjoint((1998, 1998), (2001, 2001))


# ── the gap ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text", [
    "I never told anybody how scared I was.",
    "I felt like the whole thing was over.",
    "I was terrified.",
])
def test_first_person_interior_state_is_proposed_as_uncheckable(text):
    assert router.proposes_uncheckable(text)


@pytest.mark.parametrize("text", [
    "Nobody saw the truck leave the lot that night.",   # the lot has cameras
    "Nobody knew the shop had closed.",                 # business records
    "Nobody was told about the layoffs until Monday.",  # a WARN notice exists
    "The dog was scared of the thunder.",
    "Everyone at the plant was angry about the contract.",
    "We pushed it four miles to the campground.",
])
def test_claims_about_the_world_are_not_permanent_gaps(text):
    """A false positive buries a checkable claim under the strongest sentence
    in the contract."""
    assert not router.proposes_uncheckable(text)


def test_the_gap_test_reads_the_claim_not_the_whole_statement(vault):
    """A claim about a mill closing was marked uncheckable because the
    transcript it was cut from contained an unrelated private line."""
    conn, store = vault
    body = "The mill shut in March 1998. I never told anybody how much that hurt."
    sid = desk.file_statement(conn, consent_store=store, session_id="s1",
                              narrator_id="slappy", taker_id=TAKER, body=body)
    cid = desk.add_claim(conn, consent_store=store, statement_id=sid, span=(0, 28),
                         assertion="The mill shut in March 1998.")
    assert router.route(conn, cid).status != "uncheckable_proposed"


def test_a_private_moment_is_not_talked_over_by_retrieval(vault):
    """Precedence: the gap used to sit below retrieval, so someone's private
    terror came back corroborated by a stranger who mentioned the town."""
    conn, store = vault
    _claim(conn, store, "the-colonel", "The bay at Laconia Bay is up north.")
    cid = _claim(conn, store, "slappy",
                 "At the rally. I never told anybody how scared I was at Laconia Bay.")
    assert router.route(conn, cid).status == "uncheckable_proposed"


def test_nothing_resolvable_says_nothing_about_the_vault(vault):
    """Two identical lowercase claims returned 'No source found', which is an
    assertion about the vault the router never checked."""
    conn, store = vault
    _claim(conn, store, "the-colonel", "the shop on elm street closed in the fall.")
    cid = _claim(conn, store, "slappy", "the shop on elm street closed in the fall.")
    finding = router.route(conn, cid)
    assert finding.status == "unresolved"
    assert finding.sentence() == vocabulary.UNRESOLVED


# ── it never rules ────────────────────────────────────────────────────────────

def test_routing_never_sets_a_ruler_or_a_confidence(vault):
    conn, store = vault
    cid = _claim(conn, store, "slappy", "Miller's Bar closed.")
    router.route(conn, cid)
    row = conn.execute("SELECT * FROM claims WHERE id=?", (cid,)).fetchone()
    assert row["ruled_by"] is None and row["ruled_at"] is None
    assert row["confidence"] == "medium" and row["state"] == "routed"


def test_the_router_cannot_reach_a_terminal_state(vault):
    conn, store = vault
    cid = _claim(conn, store, "slappy", "I never told anybody how scared I was.")
    assert router.route(conn, cid).status == "uncheckable_proposed"
    assert conn.execute("SELECT state FROM claims WHERE id=?",
                        (cid,)).fetchone()["state"] == "routed"
    desk.mark_uncheckable(conn, claim_id=cid, ruled_by=WITNESS, note="confirmed")
    assert conn.execute("SELECT state FROM claims WHERE id=?",
                        (cid,)).fetchone()["state"] == "uncheckable"


# ── evidence hygiene ──────────────────────────────────────────────────────────

def test_a_confirmed_gap_is_not_evidence_for_anything(vault):
    conn, store = vault
    other = _claim(conn, store, "the-colonel", "Miller's Bar had a back room.")
    desk.mark_uncheckable(conn, claim_id=other, ruled_by=WITNESS, note="no record")
    cid = _claim(conn, store, "slappy", "Miller's Bar had a back room.")
    assert router.route(conn, cid).status == "no_source_found"


def test_withheld_claims_are_not_used_as_evidence(vault):
    conn, store = vault
    other = _claim(conn, store, "the-colonel", "Miller's Bar had a back room.")
    desk.withhold(conn, claim_id=other, reason="narrator asked")
    cid = _claim(conn, store, "slappy", "Miller's Bar had a back room.")
    assert router.route(conn, cid).status == "no_source_found"


def test_routing_is_idempotent(vault):
    """Four runs left four identical rows and the queue read a stale one."""
    conn, store = vault
    _claim(conn, store, "the-colonel", "Miller's Bar had a back room.")
    cid = _claim(conn, store, "slappy", "Miller's Bar had a back room.")
    for _ in range(4):
        router.route(conn, cid)
    rows = [d for d in desk.docket(conn, cid) if d["found_by"] == "router"]
    assert len(rows) == 1


def test_route_all_sweeps_only_unrouted_claims(vault):
    conn, store = vault
    _claim(conn, store, "slappy", "Miller's Bar closed.")
    _claim(conn, store, "slappy", "The Farm flooded.")
    assert len(router.route_all(conn)) == 2
    assert router.route_all(conn) == []


# ── the queue ─────────────────────────────────────────────────────────────────

def test_the_queue_matches_the_routers_own_precedence(vault):
    conn, store = vault
    _claim(conn, store, "the-colonel", "The bay at Laconia Bay is up north.")
    cid = _claim(conn, store, "slappy",
                 "At the rally. I never told anybody how scared I was at Laconia Bay.")
    assert router.route(conn, cid).status == "uncheckable_proposed"
    assert desk.queue(conn)["gap_proposed"] == 1


def test_an_operator_cannot_forge_a_proposed_gap(vault):
    """`--excerpt "Uncheckable. …"` moved a checkable claim into the bucket
    whose instruction is 'confirm the gap and let it stand'."""
    conn, store = vault
    cid = _claim(conn, store, "slappy", "Miller's Bar closed.")
    router.route(conn, cid)
    before = desk.queue(conn)["gap_proposed"]
    desk.add_docket_entry(
        conn, claim_id=cid, relation="corroborates", source_kind="operator",
        found_by="operator", excerpt=vocabulary.UNCHECKABLE,
    )
    assert desk.queue(conn)["gap_proposed"] == before


def test_an_unrouted_claim_is_not_the_same_as_one_found_wanting(vault):
    conn, store = vault
    _claim(conn, store, "slappy", "Miller's Bar closed.")
    assert desk.queue(conn)["unrouted"] == 1
    assert desk.queue(conn)["uncorroborated"] == 0
