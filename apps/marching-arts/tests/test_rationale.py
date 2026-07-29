"""Migration 005: why the software refuses what it refuses, and what ships.

Two tables, two gates, and the difference is the design. A `facts` row is about
a PERSON and is gated by the authorization predicate. A `rationale` row is about
the SOFTWARE and is gated by whether a named human said it may leave the
building. These tests hold that line.

The fail-closed direction is the same one the resolver uses: an unclassified
record does not ship, exactly as an empty allow set compiles to 0 rather than 1.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from marching_arts import Store  # noqa: E402

MECH = "marching_arts/schema.py migration 001, CHECK on facts.band"


@pytest.fixture()
def store():
    return Store(":memory:")


def _draft(store, topic="why-no-health", **kw):
    kw.setdefault("mechanism", MECH)
    return store.record_rationale(
        topic, "Why can I not see that?", "Because a grant covers its band and "
        "everything below.", "docs/BUILD_PLAN.md", **kw)


# ── the default is not shipping ───────────────────────────────────────────────
def test_a_new_rationale_does_not_ship(store):
    """The whole gate. A record nobody classified must not reach a customer."""
    _draft(store)
    assert store.rationale() == []                       # default is shipped
    assert len(store.rationale(publication="draft")) == 1


def test_reading_defaults_to_the_shippable_set(store):
    """A caller that forgets to say what it wants gets the safe answer."""
    _draft(store, topic="a")
    _draft(store, topic="b", publication="internal")
    _draft(store, topic="c", publication="shipped", sealed_by="sean")
    assert [r.topic for r in store.rationale()] == ["c"]


def test_internal_is_a_real_third_state(store):
    """Competitive assessments of other vendors are true, correct, and not for a
    customer. Without this state they would have to be either shipped or lost."""
    _draft(store, topic="vendor-note", publication="internal")
    assert store.rationale() == []
    assert [r.topic for r in store.rationale(publication="internal")] == ["vendor-note"]


# ── shipping requires a human, and a mechanism ───────────────────────────────
def test_shipped_without_a_signer_is_refused(store):
    with pytest.raises(sqlite3.IntegrityError):
        _draft(store, publication="shipped")


def test_shipped_with_a_blank_signer_is_refused(store):
    with pytest.raises(sqlite3.IntegrityError):
        _draft(store, publication="shipped", sealed_by="   ")


def test_shipped_without_a_mechanism_is_refused(store):
    """This project's thesis as a trigger. A guarantee with no mechanism is a
    wish, and a wish does not go in the box."""
    with pytest.raises(sqlite3.IntegrityError):
        _draft(store, publication="shipped", sealed_by="sean", mechanism=None)


def test_a_blank_mechanism_is_refused_too(store):
    with pytest.raises(sqlite3.IntegrityError):
        _draft(store, publication="shipped", sealed_by="sean", mechanism="  ")


def test_an_update_cannot_smuggle_a_mechanismless_row_into_shipped(store):
    """The write path is not the only path. A row that reaches 'shipped' by
    UPDATE must clear the same bar as one that arrives by INSERT."""
    _draft(store, topic="no-mech", mechanism=None)
    with pytest.raises(sqlite3.IntegrityError):
        store.connection.execute(
            "UPDATE rationale SET publication='shipped', sealed_by='sean'"
            " WHERE topic='no-mech'")


def test_sealing_is_a_separate_act_from_writing(store):
    """The machine that drafts an answer is not the thing that decides a
    customer may read it — the same separation Nestor draws."""
    _draft(store)
    assert store.rationale() == []
    store.seal_rationale("why-no-health", "sean")
    assert [r.sealed_by for r in store.rationale()] == ["sean"]


def test_sealing_with_no_name_is_refused_before_it_reaches_sql(store):
    _draft(store)
    with pytest.raises(ValueError):
        store.seal_rationale("why-no-health", "")


# ── the same provenance rule as every fact row ───────────────────────────────
def test_a_rationale_with_no_source_is_refused(store):
    with pytest.raises(sqlite3.IntegrityError):
        store.record_rationale("t", "q?", "a", "", mechanism=MECH)


def test_an_unknown_publication_level_is_refused(store):
    with pytest.raises(sqlite3.IntegrityError):
        _draft(store, publication="public")


def test_an_unknown_level_is_refused_on_read_too(store):
    with pytest.raises(ValueError):
        store.rationale(publication="public")


def test_topic_is_unique(store):
    _draft(store, topic="dup")
    with pytest.raises(sqlite3.IntegrityError):
        _draft(store, topic="dup")


# ── the two gates do not touch ───────────────────────────────────────────────
def test_rationale_is_not_gated_by_the_authorization_predicate(store):
    """A shipped rationale is readable without any grant, because it is about the
    software rather than about a person. If this ever needed a Principal, the two
    concepts would have been confused."""
    _draft(store, publication="shipped", sealed_by="sean")
    assert len(store.rationale()) == 1        # no Principal anywhere in the call


def test_rationale_rows_are_not_facts(store):
    """They live in a different table, so a rationale can never appear in a
    member's record and a member's record can never be published by sealing."""
    _draft(store, publication="shipped", sealed_by="sean")
    assert store.connection.execute("SELECT COUNT(*) FROM facts").fetchone()[0] == 0


# ── the schema's own default, which no method call reaches ────────────────────
#
# record_rationale() carries a Python default of "draft" and always passes it
# explicitly, so the DEFAULT in migration 005 is never exercised through the
# module. It exists for the writer who bypasses the module — the same class of
# writer every trigger in this schema is aimed at — and it was untested until a
# mutation flipped it to 'shipped' and all 129 tests still passed.

def test_a_raw_insert_with_no_publication_lands_as_draft(store):
    """The fail-closed default, exercised the only way it can be."""
    store.connection.execute(
        "INSERT INTO rationale(topic, question, answer, mechanism, source)"
        " VALUES ('raw', 'q?', 'a', ?, 'test')", (MECH,))
    store.connection.commit()
    assert store.rationale() == []
    assert [r.topic for r in store.rationale(publication="draft")] == ["raw"]


def test_a_raw_insert_cannot_reach_shipped_without_a_signer(store):
    """And the default is not the only thing standing in the way."""
    with pytest.raises(sqlite3.IntegrityError):
        store.connection.execute(
            "INSERT INTO rationale(topic, question, answer, mechanism, source,"
            " publication) VALUES ('raw2', 'q?', 'a', ?, 'test', 'shipped')",
            (MECH,))
