"""P1's gate: hidden rows must not leak through a COUNT, a filter, a sort order
or an empty state.

These are the tests that decide whether the phase is done. Every other test in
this directory checks that the code works; these check that it cannot be made to
misbehave. If one of them starts failing, the leak is back.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from marching_arts import Band, GrantState, Principal, Store  # noqa: E402

LEADER = Principal("leader")
STRANGER = Principal("stranger")


@pytest.fixture()
def store():
    """Two members. The leader holds a sealed craft-band grant on one of them."""
    s = Store(":memory:")
    for i in range(3):
        s.record_fact("visible-member", Band.CRAFT, "rehearsal log",
                      payload=f"visible {i}")
    for i in range(7):
        s.record_fact("hidden-member", Band.CRAFT, "rehearsal log",
                      payload=f"hidden {i}")
    s.record_grant("visible-member", "leader", Band.CRAFT,
                   GrantState.SEALED.value, "consent form", sealed_by="guardian")
    return s


# ── count ───────────────────────────────────────────────────────────────────
def test_count_excludes_hidden_rows(store):
    assert store.count(LEADER) == 3
    assert store.count(STRANGER) == 0


def test_count_is_computed_in_sql_not_in_python(store):
    """The gate's exact wording: if the count is computed over fetched rows,
    the phase is not done.

    Traced rather than asserted. A COUNT(*) that reaches SQLite carrying the
    authorization predicate cannot have fetched the hidden rows to get there.
    """
    seen: list[str] = []
    store.connection.set_trace_callback(seen.append)
    try:
        store.count(LEADER)
    finally:
        store.connection.set_trace_callback(None)

    statements = [s for s in seen if "facts" in s]
    assert len(statements) == 1, f"count issued {len(statements)} queries: {statements}"
    sql = statements[0]
    assert "COUNT(*)" in sql.upper()
    # The predicate travelled with it — the database did the filtering.
    assert "grants" in sql and "subject_id" in sql


def test_count_matches_visible_length(store):
    """The cheap version must agree with the honest one, or one of them lies."""
    for principal in (LEADER, STRANGER, Principal("visible-member")):
        assert store.count(principal) == len(store.visible(principal))


# ── filter ──────────────────────────────────────────────────────────────────
def test_caller_filter_cannot_widen_the_result(store):
    """A caller-supplied filter is ANDed inside the predicate, so the classic
    ``OR 1=1`` narrows nothing and reveals nothing."""
    rows = store.visible(LEADER, where="1 = 1 OR 1 = 1")
    assert len(rows) == 3
    assert {r.subject_id for r in rows} == {"visible-member"}


def test_caller_filter_targeting_a_hidden_subject_returns_nothing(store):
    rows = store.visible(LEADER, where="facts.subject_id = :who",
                         params={"who": "hidden-member"})
    assert rows == []
    assert store.count(LEADER, where="facts.subject_id = :who",
                       params={"who": "hidden-member"}) == 0


def test_filter_cannot_confirm_a_hidden_row_by_probing(store):
    """Probing for a payload you are not allowed to see must answer the same way
    whether or not the payload exists."""
    present = store.count(LEADER, where="facts.payload = :p", params={"p": "hidden 0"})
    absent = store.count(LEADER, where="facts.payload = :p", params={"p": "no such row"})
    assert present == absent == 0


# ── sort order ──────────────────────────────────────────────────────────────
def test_sort_column_is_allowlisted(store):
    with pytest.raises(ValueError):
        store.visible(LEADER, order_by="(SELECT payload FROM facts LIMIT 1)")


def test_pagination_does_not_reveal_gaps(store):
    """LIMIT/OFFSET apply after the predicate, so pages are dense.

    If hidden rows participated in ordering, the second page here would be short
    or empty and the caller could infer how many rows they were not shown.
    """
    pages = [store.visible(LEADER, limit=2, offset=o) for o in (0, 2, 4)]
    assert [len(p) for p in pages] == [2, 1, 0]
    ids = [row.id for page in pages for row in page]
    assert ids == sorted(ids)
    assert len(ids) == store.count(LEADER)


def test_descending_sort_reveals_no_more_than_ascending(store):
    up = store.visible(LEADER, order_by="id")
    down = store.visible(LEADER, order_by="id", descending=True)
    assert [r.id for r in up] == list(reversed([r.id for r in down]))


# ── empty state ─────────────────────────────────────────────────────────────
def test_refused_and_nonexistent_are_indistinguishable(store):
    """The one people forget.

    A member who declined to share must look exactly like a member who is not in
    the system. If they look different, declining becomes the signal, and every
    member who exercises the choice is marked by exercising it.
    """
    refused = store.visible(LEADER, where="facts.subject_id = :s",
                            params={"s": "hidden-member"})
    absent = store.visible(LEADER, where="facts.subject_id = :s",
                           params={"s": "no-such-person"})
    assert refused == absent == []
    assert store.count(LEADER, where="facts.subject_id = :s",
                       params={"s": "hidden-member"}) == \
           store.count(LEADER, where="facts.subject_id = :s",
                       params={"s": "no-such-person"}) == 0


def test_subject_list_omits_rather_than_blanks(store):
    """No empty slot where a declined grant would render."""
    assert store.subjects(LEADER) == ["visible-member"]
    assert store.subjects(STRANGER) == []


def test_draft_grant_is_indistinguishable_from_no_grant(store):
    """Only a human seals. A grant the system inferred is recorded and inert."""
    store.record_grant("hidden-member", "leader", Band.CRAFT,
                       GrantState.DRAFT.value, "inferred from roster")
    assert store.subjects(LEADER) == ["visible-member"]
    assert store.count(LEADER) == 3


def test_revocation_is_silent_and_immediate(store):
    assert store.count(LEADER) == 3
    store.revoke("visible-member", "leader")
    assert store.count(LEADER) == 0
    assert store.subjects(LEADER) == []
    # No residue: the former grant is not readable as a former grant.
    assert store.connection.execute(
        "SELECT COUNT(*) FROM grants WHERE grantee_id = 'leader'"
    ).fetchone()[0] == 0


# ── fail closed ─────────────────────────────────────────────────────────────
def test_unknown_principal_sees_nothing(store):
    assert store.visible(Principal("")) == []
    assert store.count(Principal("nobody")) == 0


def test_a_grant_cannot_open_a_never_served_band(store):
    """The deny applies to the union of allows, so no grant can win against it."""
    store.record_fact("visible-member", Band.SAFEGUARDING, "routed elsewhere",
                      payload="must never be served")
    store.record_grant("visible-member", "leader", Band.FAMILY,
                       GrantState.SEALED.value, "consent form", sealed_by="guardian")
    rows = store.visible(LEADER)
    assert all(r.band != int(Band.SAFEGUARDING) for r in rows)
    assert store.count(LEADER, where="facts.band = :b",
                       params={"b": int(Band.SAFEGUARDING)}) == 0
