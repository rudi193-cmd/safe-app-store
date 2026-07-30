"""Migration 007: corrections land beside the record, never on top of it.

That is one of this project's own rules and migration 005 shipped a table that
structurally could not keep it — ``rationale.topic`` is UNIQUE with no supersedes
column, so a correction could not be a second row, and amending the existing one
**overwrote** the text it replaced. A log that quietly overwrites its own
mistakes can confirm the current answer and cannot be used to check whether the
reasoning was sound. 005 was built to ship reasoning and made exactly that
mistake.

Three things these tests hold, in order of how much they matter:

1. **The prior text survives an amendment**, and it survives because of a
   trigger rather than because a caller remembered. A convention would be enough
   for a careful caller, and a careful caller was never the problem.
2. **"We disclose what we got wrong" is a query**, not a paragraph. It is a
   guarantee like any other, so it needs a mechanism or it is a wish — and a
   claim nobody can enumerate is not checkable.
3. **What ships is decided by a discriminator, not by taste.** Does the mistake
   change what a reader should believe about a current guarantee? A live defect
   stays internal in every case.

**What these tests cannot see.** Whether a *human* classified a given correction
correctly. The schema can refuse a shipped row with no mechanism, no signer, or
no shipped subject; it cannot know whether "this was embarrassing" was filed as
internal to avoid saying it. ``sealed_by`` is the whole answer to that — a named
person signs each row out — and no test can stand in for one.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from marching_arts import Store  # noqa: E402

MECH = "policy.Policy.projection, DERIVE_AT"
FIX = "tests/test_auth.py::test_a_role_still_buys_nothing_in_the_default_policy"
TOPIC = "why-no-health"
FIRST = "Because L4 is named persons only."


@pytest.fixture()
def store():
    return Store(":memory:")


@pytest.fixture()
def shipped(store):
    """A guarantee that has shipped, which is what a correction attaches to."""
    store.record_rationale(
        TOPIC, "Why can I not see that?", FIRST, "docs/BUILD_PLAN.md",
        mechanism=MECH, publication="shipped", sealed_by="sean")
    return store


def _correct(store, topic=TOPIC, **kw):
    kw.setdefault("mechanism", FIX)
    return store.record_correction(
        topic, "the tripwire that was supposed to force a roles table could not"
        " fail: the fixture had no row the principal could not already see",
        "PR #127", **kw)


# ── 1. the prior text survives, and a trigger is why ─────────────────────────

def test_amending_a_shipped_answer_keeps_what_it_used_to_say(shipped):
    """The failure this migration exists to remove. Before 007 this text was gone."""
    shipped.amend_rationale(
        TOPIC, "L4 is named persons only, and no role reaches it.", mechanism=MECH)
    kept = shipped.corrections(publication="draft")
    assert len(kept) == 1
    assert kept[0].superseded_answer == FIRST
    assert kept[0].superseded_mechanism == MECH
    assert shipped.rationale()[0].answer.endswith("no role reaches it.")


def test_the_prior_text_survives_a_writer_who_never_heard_of_amend_rationale(shipped):
    """A trigger and not a convention, so it holds for raw SQL too. ``amend_rationale``
    exists to make the honest path obvious, not to be the mechanism."""
    shipped.connection.execute(
        "UPDATE rationale SET answer = 'rewritten by hand' WHERE topic = ?", (TOPIC,))
    shipped.connection.commit()
    assert [c.superseded_answer for c in shipped.corrections(publication="draft")] == [FIRST]


def test_the_trigger_writes_a_stub_that_cannot_ship(shipped):
    """The machine can see *that* the text changed and cannot know *what was
    wrong*. So it lands as draft carrying a placeholder, and a human fills in the
    reason and seals it. Auto-shipping "this was amended" would fill the box with
    rows that mean nothing."""
    shipped.amend_rationale(TOPIC, "second answer", mechanism=MECH)
    assert shipped.corrections() == []                        # shipped: nothing
    stub = shipped.corrections(publication="draft")[0]
    assert "say what was wrong" in stub.what_was_wrong
    assert stub.mechanism is None


def test_a_publication_change_alone_writes_no_correction(store):
    """Sealing a draft, or withdrawing a shipped row, leaves the answer alone.
    Those are publication decisions rather than amendments, and a correction for
    every seal would bury the real ones."""
    store.record_rationale(TOPIC, "q?", FIRST, "src", mechanism=MECH)
    store.seal_rationale(TOPIC, "sean")
    assert store.corrections(publication="draft") == []
    store.connection.execute(
        "UPDATE rationale SET publication = 'internal' WHERE topic = ?", (TOPIC,))
    store.connection.commit()
    assert store.corrections(publication="draft") == []


def test_amending_an_unshipped_answer_writes_no_correction(store):
    """A draft being edited is drafting. Nobody was told the old text, so there is
    nothing to have taken back."""
    store.record_rationale(TOPIC, "q?", FIRST, "src", mechanism=MECH)
    store.amend_rationale(TOPIC, "a better draft", mechanism=MECH)
    assert store.corrections(publication="draft") == []


def test_a_guarantee_can_be_wrong_more_than_once(shipped):
    """``topic`` is deliberately not unique here. Collapsing two corrections into
    one row would be the overwrite bug again, one level down."""
    shipped.amend_rationale(TOPIC, "second", mechanism=MECH)
    shipped.connection.execute(
        "UPDATE rationale SET publication = 'shipped', sealed_by = 'sean'"
        " WHERE topic = ?", (TOPIC,))
    shipped.amend_rationale(TOPIC, "third", mechanism=MECH)
    kept = [c.superseded_answer for c in shipped.corrections(publication="draft")]
    assert kept == [FIRST, "second"]


def test_a_correction_does_not_edit_the_guarantee(shipped):
    """Filing one leaves the current answer exactly where it was — which is the
    difference between beside and on top."""
    _correct(shipped, publication="internal")
    assert shipped.rationale()[0].answer == FIRST


# ── 2. the candour claim is a query ──────────────────────────────────────────

def test_every_guarantee_that_was_ever_wrong_is_enumerable(shipped):
    """The one query 007 exists for. Buried in prose, a guarantee with a clean
    history and one that was wrong for six months read identically."""
    shipped.record_rationale(
        "why-partitioned", "Why per subject?", "So one member can be forgotten.",
        "docs/BUILD_PLAN.md", mechanism="migration 004",
        publication="shipped", sealed_by="sean")
    assert shipped.corrected_topics() == []
    cid = _correct(shipped)
    shipped.seal_correction(cid, "sean")
    assert shipped.corrected_topics() == [TOPIC]
    assert "why-partitioned" not in shipped.corrected_topics()


def test_an_unshipped_correction_is_not_counted_as_disclosed(shipped):
    """An internal correction is a real record and is not a disclosure. Counting
    it as one would let the checkable claim be satisfied by rows no customer can
    read, which is worse than not making the claim."""
    _correct(shipped, publication="internal")
    assert shipped.corrected_topics() == []
    assert shipped.corrected_topics(publication="internal") == [TOPIC]


def test_corrections_default_to_the_shippable_set(shipped):
    """Same default as ``rationale()``: a caller who forgets what they want gets
    the safe answer."""
    _correct(shipped, publication="internal")
    assert shipped.corrections() == []
    assert len(shipped.corrections(publication="internal")) == 1


def test_corrections_can_be_read_for_one_guarantee(shipped):
    shipped.record_rationale("other", "q?", "a", "src", mechanism=MECH,
                             publication="shipped", sealed_by="sean")
    shipped.seal_correction(_correct(shipped), "sean")
    shipped.seal_correction(_correct(shipped, topic="other"), "sean")
    assert [c.topic for c in shipped.corrections(topic=TOPIC)] == [TOPIC]
    assert len(shipped.corrections()) == 2


def test_an_unknown_publication_level_is_refused_on_both_reads(shipped):
    for call in (lambda: shipped.corrections(publication="public"),
                 lambda: shipped.corrected_topics(publication="public")):
        with pytest.raises(ValueError):
            call()


# ── 3. what may ship ────────────────────────────────────────────────────────

def test_a_shipped_correction_must_name_what_fixed_it(shipped):
    """005's thesis pointed at a different noun. For a guarantee the mechanism is
    what makes the answer true; for a correction it is what stopped it being
    false. "We fixed it" is not checkable and a named test is."""
    with pytest.raises(sqlite3.IntegrityError):
        _correct(shipped, publication="shipped", sealed_by="sean", mechanism=None)
    with pytest.raises(sqlite3.IntegrityError):
        _correct(shipped, publication="shipped", sealed_by="sean", mechanism="   ")


def test_an_update_cannot_smuggle_a_mechanismless_correction_into_shipped(shipped):
    cid = _correct(shipped, mechanism=None)
    with pytest.raises(sqlite3.IntegrityError):
        shipped.connection.execute(
            "UPDATE rationale_correction SET publication='shipped',"
            " sealed_by='sean' WHERE id = ?", (cid,))


def test_a_shipped_correction_needs_a_signer(shipped):
    with pytest.raises(sqlite3.IntegrityError):
        _correct(shipped, publication="shipped")
    with pytest.raises(sqlite3.IntegrityError):
        _correct(shipped, publication="shipped", sealed_by="  ")


def test_sealing_with_no_name_is_refused_before_it_reaches_sql(shipped):
    cid = _correct(shipped)
    with pytest.raises(ValueError):
        shipped.seal_correction(cid, "")


def test_a_correction_cannot_ship_ahead_of_the_guarantee_it_corrects(store):
    """Disclosing a defect in work nobody has seen is disclosure with none of the
    benefit. Fail-closed direction: hold the correction back, do not push the
    guarantee out."""
    store.record_rationale(TOPIC, "q?", FIRST, "src", mechanism=MECH)  # draft
    with pytest.raises(sqlite3.IntegrityError):
        _correct(store, publication="shipped", sealed_by="sean")
    cid = _correct(store, publication="internal")
    with pytest.raises(sqlite3.IntegrityError):
        store.seal_correction(cid, "sean")
    store.seal_rationale(TOPIC, "sean")                    # now the subject ships
    store.seal_correction(cid, "sean")
    assert store.corrected_topics() == [TOPIC]


def test_a_correction_to_nothing_cannot_be_filed(store):
    """A foreign key, so a correction floating free of any guarantee is refused."""
    with pytest.raises(sqlite3.IntegrityError):
        _correct(store, topic="no-such-guarantee", publication="internal")


def test_a_blank_reason_is_refused(shipped):
    for bad in ("", "   "):
        with pytest.raises(sqlite3.IntegrityError):
            shipped.record_correction(TOPIC, bad, "PR #127", mechanism=FIX)


def test_a_correction_with_no_source_is_refused(shipped):
    with pytest.raises(sqlite3.IntegrityError):
        shipped.record_correction(TOPIC, "something was wrong", "", mechanism=FIX)


def test_an_unknown_publication_level_is_refused_on_write(shipped):
    with pytest.raises(sqlite3.IntegrityError):
        _correct(shipped, publication="public")


def test_a_raw_insert_with_no_publication_lands_as_draft(shipped):
    """The schema's own default, exercised the only way it can be — the module
    always passes ``publication`` explicitly, so a mutation flipping the DEFAULT
    to 'shipped' would otherwise pass every test. Migration 005's version of this
    was untested until exactly that mutation found it."""
    shipped.connection.execute(
        "INSERT INTO rationale_correction(topic, what_was_wrong, mechanism, source)"
        " VALUES (?, 'raw', ?, 'test')", (TOPIC, FIX))
    shipped.connection.commit()
    assert shipped.corrections() == []
    assert [c.what_was_wrong for c in shipped.corrections(publication="draft")] == ["raw"]


# ── the two gates still do not touch ────────────────────────────────────────

def test_a_correction_is_not_a_fact_about_a_person(shipped):
    """Different table, so a correction can never surface in a member's record and
    a member's record can never be published by sealing a correction."""
    shipped.seal_correction(_correct(shipped), "sean")
    assert shipped.connection.execute(
        "SELECT COUNT(*) FROM facts").fetchone()[0] == 0


def test_reading_corrections_needs_no_principal(shipped):
    """A correction is about the software, so it is gated by whether a named human
    released it — not by the authorization predicate. If this ever needed a
    ``Principal`` the two concepts would have been confused."""
    shipped.seal_correction(_correct(shipped), "sean")
    assert len(shipped.corrections()) == 1        # no Principal anywhere in the call
