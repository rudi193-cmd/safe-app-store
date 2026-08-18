"""H-4 — a dose is a fact with a source; and the pack classifies at import (bite 3).

Promoted out of `test_invariants_pending.py` when
`homestead_health.packs.immunizations` landed, the health module's second
promotion. The `test_h4_…` body is kept as it was written in the pending file;
around it is the custody pack's test, one schema over — because the claim is the
same claim (*"an unclassified field fails the build naming itself"*, I-11), now
on health's first real schema rather than the law module's.

The rungs checked below are the plan's own proposed table
(`homestead/docs/PLAN-homestead-health.md` § "The immunizations pack,
classified"), not this file's invention. The bite's *done when*: the pack
imports, and deleting one field's rung fails the build with that field named —
the custody check, on the second real schema.
"""
from __future__ import annotations

import copy

import pytest

from homestead.keep.rungs import Rung, classify_schema

from homestead_health.packs import immunizations


# ── H-4, promoted verbatim ───────────────────────────────────────────────────


def test_h4_every_dose_names_how_it_is_known():
    from homestead_health.packs.immunizations import SCHEMA

    assert "source" in SCHEMA, "a dose with no source field cannot record how it is known"
    declaration = SCHEMA["source"]
    assert declaration["rung"] is not None
    assert declaration["why"], "a declaration without its sentence is not reviewable"


# ── the pack, classified at import ───────────────────────────────────────────


def test_the_pack_classifies_at_import():
    """`FIELDS` exists because `classify_schema(SCHEMA)` ran at module top level —
    a pack that deferred classification to a caller would move the build failure to
    runtime, which is the whole thing this bite exists to prevent."""
    assert isinstance(immunizations.FIELDS, dict)
    assert immunizations.FIELDS
    assert all(isinstance(r, Rung) for r in immunizations.FIELDS.values())
    assert set(immunizations.FIELDS) == set(immunizations.SCHEMA)


def test_the_schema_matches_the_plans_proposed_table():
    """Field by field against the plan's table. The subject id is the derived form
    of the person (L3); the vaccine is a medical act attached to a person (L4);
    dates name nobody by themselves (L2) while the record composes to L4 by max;
    provider and source resolve to a person/household with no category (L3); notes
    inherit the custody decision (L4)."""
    expected = {
        "subject": Rung.L3,     # the opaque roster id — resolves to a person, no category
        "vaccine": Rung.L4,     # a medical act attached to a person
        "dose_date": Rung.L2,   # a date, naming nobody by itself
        "next_due": Rung.L2,    # same posture; a parsed Deadline
        "provider": Rung.L3,    # a care relationship resolving to the household
        "lot_number": Rung.L2,  # operational; no identity, no category
        "source": Rung.L3,      # provenance — resolves to who was there, no category
        "notes": Rung.L4,       # free operator text; the custody.notes decision
    }
    assert immunizations.FIELDS == expected


def test_the_dangerous_rungs_are_where_they_must_be():
    """Spot-checks stated on their own so a change to them fails by name. The
    vaccine and the notes are the L4 content the whole model turns on not rendering
    by default; a date must stay L2 so the record — not the bare date — is what the
    surfaces gate."""
    assert immunizations.FIELDS["vaccine"] is Rung.L4, "a vaccine is a medical act on a person"
    assert immunizations.FIELDS["notes"] is Rung.L4, "operator notes carry protected categories (F-4)"
    assert immunizations.FIELDS["subject"] is Rung.L3, "the subject id resolves to a person"


def test_no_key_material_lives_in_this_pack():
    """The plan's exclusion 3, made a test: no ssn, no member id, no insurance
    field. Key material is L5 and belongs to the insurance pack when it exists;
    importing one field of it early is the two-homes drift the exclusion refuses,
    and there is no L5 field here to be that first import."""
    forbidden = {"ssn", "member_id", "member_number", "policy_number", "insurance"}
    assert not (forbidden & set(immunizations.SCHEMA)), (
        "key material belongs to the insurance pack at L5, not here"
    )
    assert Rung.L5 not in immunizations.FIELDS.values(), (
        "immunizations is the least dangerous content in the domain — nothing here is L5"
    )


def test_every_field_records_matter_and_jurisdiction():
    """Step 5 of the classification procedure: the rung is recorded *with* the
    matter type and jurisdiction, because step 1 depends on both and neither is
    derivable from the field name. A pack that dropped them would be un-reviewable."""
    for name, spec in immunizations.SCHEMA.items():
        assert spec.get("matter") == "immunizations", name
        assert spec.get("jurisdiction"), name
        assert spec.get("why"), f"{name} declares a rung with no recorded reason"


def test_deleting_a_fields_rung_fails_the_build_naming_it():
    """The bite's *done when*, exactly: strip one field's rung and the pack no
    longer classifies — and the failure names the field, so the fix is where the
    omission is and not a hunt. This is I-11 at import, on health's schema."""
    for victim in immunizations.SCHEMA:
        wounded = copy.deepcopy(immunizations.SCHEMA)
        del wounded[victim]["rung"]
        with pytest.raises(Exception) as caught:
            classify_schema(wounded)
        assert victim in str(caught.value), (
            f"stripping {victim}'s rung must fail the build and name {victim}"
        )


def test_a_name_based_default_is_not_what_saved_this_pack():
    """The rungs are declared, not inferred. Proof: the same field names, with
    their declarations removed, all fail — so nothing here is keyed on a name
    looking hot or cool. classify_schema never guesses from a name."""
    for name in immunizations.SCHEMA:
        with pytest.raises(Exception):
            classify_schema({name: None})
