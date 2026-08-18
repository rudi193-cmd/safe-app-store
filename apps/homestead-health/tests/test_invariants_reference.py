"""H-5 — reference data is pinned, never fetched.

Promoted out of `test_invariants_pending.py` when `homestead_health.reference`
landed — the pinned immunization-schedule snapshot. The `test_h5_…` body is kept
as written; around it are the checks that make H-5 a real invariant rather than a
version string: the snapshot holds no subject, reads no clock, and dials for
nothing. Traceable to I-17 (never dials), I-26 (imports no network), and the
face-3 seam (public reference is the almanac's catalog to locate; this repo pins
only the snapshot it needs).
"""
from __future__ import annotations

import ast
from datetime import date
from pathlib import Path

from homestead_health.reference import SCHEDULE, Schedule, ScheduledDose

MODULE = Path(__file__).resolve().parent.parent / "homestead_health" / "reference.py"


# ── H-5, promoted verbatim ───────────────────────────────────────────────────


def test_h5_the_snapshot_shows_its_own_date():
    from homestead_health.reference import SCHEDULE as S

    assert S.version, "a snapshot that cannot say which version it is, isn't one"
    assert S.as_of, "a snapshot that cannot say its date is a live feed in disguise"


# ── the version and date are a fixed pin, not the clock ──────────────────────


def test_the_as_of_date_is_a_pinned_literal_not_the_clock():
    """`as_of` is a `datetime.date`, and a *fixed* one — the same value on every
    read. A snapshot whose date moved with the wall clock would be a live feed
    wearing a date field, which is the exact thing H-5 forbids."""
    assert isinstance(SCHEDULE.as_of, date)
    assert SCHEDULE.as_of == SCHEDULE.as_of  # stable, not a property reading now()
    # And the module reads no clock at all — no date.today()/datetime.now()/now().
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    clock_reads = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
            if name in {"today", "now", "utcnow"}:
                clock_reads.append(node.lineno)
    assert not clock_reads, (
        f"reference.py reads the clock at lines {clock_reads}; a pinned snapshot "
        "states its own date and never reads the machine's"
    )


def test_the_citation_names_the_version_and_the_date():
    """The one line schedule reasoning cites (the plan's Today example) carries the
    source, the version, and the pinned date — so any answer quoting the schedule
    says which snapshot it came from."""
    cite = SCHEDULE.citation()
    assert SCHEDULE.version in cite
    assert SCHEDULE.as_of.isoformat() in cite
    assert SCHEDULE.source in cite


# ── the snapshot holds no subject ────────────────────────────────────────────


def test_the_snapshot_holds_no_subject_by_shape():
    """Public reference is keyed by vaccine, not by person. Neither the schedule nor
    a dose has any field that could carry a subject — there is structurally nowhere
    to put one, which is what keeps the reference lane on the safe side of H-2's
    wall (it cannot join to a child because it holds no child)."""
    schedule_fields = set(Schedule.__dataclass_fields__)
    dose_fields = set(ScheduledDose.__dataclass_fields__)
    for banned in ("subject", "subj", "person", "child", "patient", "name"):
        assert banned not in schedule_fields, f"Schedule must hold no {banned}"
        assert banned not in dose_fields, f"a dose must hold no {banned}"


def test_no_subject_id_appears_anywhere_in_the_pinned_data():
    """Belt to the structural braces: nothing that looks like a roster subject id
    (`subj-NN`) appears in the rendered snapshot. Public reference carries no
    reference to a household member, by construction."""
    blob = repr(SCHEDULE)
    assert "subj-" not in blob
    assert "subject" not in blob.lower()


# ── it dials for nothing ─────────────────────────────────────────────────────


def test_the_module_imports_no_network():
    """I-17/I-26 at this module specifically (the seat scan covers the package; this
    states it for the snapshot, where 'never fetched' is the whole point). No
    network module, no fetch, no url-resolving call anywhere in reference.py."""
    net = {"socket", "ssl", "urllib", "http", "requests", "httpx", "aiohttp",
           "websockets", "urllib3", "ftplib", "smtplib"}
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert not (net & imported), f"reference.py imports a network module: {net & imported}"


# ── the pinned data is real, well-formed, and immutable ──────────────────────


def test_the_snapshot_is_non_empty_and_well_formed():
    """A snapshot of nothing is not a snapshot. Every dose names a vaccine, which
    dose it is, and a recommended age — the three fields a schedule row needs to be
    reference at all."""
    assert SCHEDULE.doses, "the pinned schedule has no doses"
    for d in SCHEDULE.doses:
        assert d.vaccine and d.dose and d.recommended_age, f"a dose is missing a field: {d}"


def test_for_vaccine_is_a_pure_lookup_that_takes_no_subject():
    """The lookup takes a vaccine name and returns its doses in order — a query over
    public reference, never joined to a person. MMR's two doses are the worked
    example (dose 1 at 12-15 months, dose 2 at 4-6 years)."""
    mmr = SCHEDULE.for_vaccine("MMR")
    assert len(mmr) == 2
    assert [d.dose for d in mmr] == ["dose 1 of 2", "dose 2 of 2"]
    assert SCHEDULE.for_vaccine("NoSuchVaccine") == ()
    assert "MMR" in SCHEDULE.vaccines()


def test_the_snapshot_is_immutable():
    """Updating the snapshot is an operator's act — a new pinned literal in a dated
    commit — not a runtime mutation. The frozen dataclass makes that structural: the
    pin cannot be edited in place."""
    import dataclasses
    import pytest

    with pytest.raises(dataclasses.FrozenInstanceError):
        SCHEDULE.version = "tampered"  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        SCHEDULE.doses[0].vaccine = "tampered"  # type: ignore[misc]
