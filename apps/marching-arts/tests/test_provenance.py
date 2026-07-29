"""Provenance and derivation: the two guarantees the schema enforces itself.

Both of these are checked by SQLite rather than by application code, which is
the difference between a guarantee and a convention. A future caller who forgets
cannot break them, and neither can a future maintainer who does not know they
exist.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from marching_arts import Band, GrantState, Principal, Store  # noqa: E402
from marching_arts.bands import DERIVE_AT, parse  # noqa: E402


@pytest.fixture()
def store():
    return Store(":memory:")


# ── a fact with no source is a rumour with a primary key ────────────────────
def test_fact_without_source_is_rejected(store):
    with pytest.raises(sqlite3.IntegrityError):
        store.record_fact("member", Band.ROSTER, "", payload="x")


def test_fact_with_whitespace_source_is_rejected(store):
    with pytest.raises(sqlite3.IntegrityError):
        store.record_fact("member", Band.ROSTER, "   ", payload="x")


def test_source_survives_the_read(store):
    store.record_fact("member", Band.ROSTER, "2026 registration form", payload="lead")
    row = store.visible(Principal("member"))[0]
    assert row.source == "2026 registration form"


def test_band_outside_the_scale_is_rejected(store):
    with pytest.raises(sqlite3.IntegrityError):
        store.record_fact("member", 99, "somewhere", payload="x")


def test_parse_refuses_to_default(store):
    """A band that cannot be resolved must not silently become SELF."""
    with pytest.raises((KeyError, ValueError)):
        parse("not-a-band")


# ── only a human seals ──────────────────────────────────────────────────────
def test_sealed_grant_requires_a_signer(store):
    with pytest.raises(sqlite3.IntegrityError):
        store.record_grant("member", "leader", Band.CRAFT,
                           GrantState.SEALED.value, "consent form")


def test_draft_grant_needs_no_signer(store):
    """Draft is what the machine may produce. It just cannot authorize anything."""
    store.record_grant("member", "leader", Band.CRAFT,
                       GrantState.DRAFT.value, "inferred from roster")
    assert store.count(Principal("leader")) == 0


def test_grant_state_is_constrained(store):
    with pytest.raises(sqlite3.IntegrityError):
        store.record_grant("member", "leader", Band.CRAFT,
                           "approved", "made-up state", sealed_by="someone")


# ── derive the instruction, do not forward the fact ─────────────────────────
def test_accommodation_payload_is_withheld_but_the_instruction_is_not(store):
    store.record_fact("member", DERIVE_AT, "medical note on file",
                      payload="the diagnosis",
                      instruction="rotate out of the block every twenty minutes")
    store.record_grant("member", "leader", Band.FAMILY,
                       GrantState.SEALED.value, "consent form", sealed_by="guardian")

    row = store.visible(Principal("leader"))[0]
    assert row.payload is None, "the fact itself must not leave the database"
    assert row.instruction == "rotate out of the block every twenty minutes"


def test_the_subject_still_sees_their_own_fact(store):
    """Consent governs disclosure to others. It does not stand between someone
    and their own information."""
    store.record_fact("member", DERIVE_AT, "medical note on file",
                      payload="the diagnosis", instruction="rotate out")
    row = store.visible(Principal("member"))[0]
    assert row.payload == "the diagnosis"


def test_lower_bands_are_forwarded_normally(store):
    store.record_fact("member", Band.CRAFT, "rehearsal log", payload="left-foot lead")
    store.record_grant("member", "leader", Band.CRAFT,
                       GrantState.SEALED.value, "consent form", sealed_by="guardian")
    assert store.visible(Principal("leader"))[0].payload == "left-foot lead"


# ── grants resolve per record, not per user ─────────────────────────────────
def test_a_leader_is_also_a_member(store):
    """The same person, in one query, as subject of their own rows and grantee
    of someone else's."""
    store.record_fact("leader", Band.HEALTH, "registration", payload="own record")
    store.record_fact("member", Band.CRAFT, "rehearsal log", payload="squad record")
    store.record_grant("member", "leader", Band.CRAFT,
                       GrantState.SEALED.value, "consent form", sealed_by="guardian")

    rows = {r.subject_id: r for r in store.visible(Principal("leader"))}
    assert set(rows) == {"leader", "member"}
    assert rows["leader"].payload == "own record"      # subject: full access
    assert rows["member"].payload == "squad record"    # grantee: within the grant


def test_a_grant_does_not_reach_above_its_band(store):
    store.record_fact("member", Band.HEALTH, "registration", payload="private")
    store.record_grant("member", "leader", Band.CRAFT,
                       GrantState.SEALED.value, "consent form", sealed_by="guardian")
    assert store.count(Principal("leader")) == 0


def test_roles_alone_grant_nothing(store):
    """L4 is named persons only — not caption heads, not program coordinators,
    not roles."""
    store.record_fact("member", Band.HEALTH, "registration", payload="private")
    head = Principal("caption-head", roles=frozenset({"caption_head", "director"}))
    assert store.count(head) == 0
