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

import pytest

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


def test_as_of_is_a_literal_date_not_a_computed_value():
    """The H-5 audit's load-bearing fix. The name-based scan above catches a bare
    `date.today()`; it does *not* catch `getattr(date, "today")()` or a two-line
    helper in a sibling module — both of which the audit ran, watching `as_of`
    become `date.today()` while every test stayed green. So the pin is enforced by
    *shape*: `as_of` must parse as `date(<all-literal args>)` and nothing else — a
    name, a `getattr(...)()`, or any other call fails, because none of them is a
    literal date."""
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    as_of = None
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "SCHEDULE" for t in node.targets)
            and isinstance(node.value, ast.Call)
        ):
            for kw in node.value.keywords:
                if kw.arg == "as_of":
                    as_of = kw.value
    assert as_of is not None, "SCHEDULE must set as_of explicitly"
    assert isinstance(as_of, ast.Call), (
        "as_of must be a literal date(y, m, d) — a name or a computed value is a "
        "live feed wearing a pin"
    )
    callee = as_of.func
    callee_name = callee.attr if isinstance(callee, ast.Attribute) else getattr(callee, "id", "")
    assert callee_name == "date", f"as_of must be a date(...) literal, got a call to {callee_name!r}()"
    assert as_of.args and all(isinstance(a, ast.Constant) for a in as_of.args), (
        "as_of's date(...) takes only literal arguments — a computed or "
        "clock-derived date is exactly what a pin must not be"
    )
    assert not as_of.keywords, "as_of is date(y, m, d) — positional literals only"


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
    """Structural, and an **allowlist** — the H-5 audit's fix. Public reference is
    keyed by vaccine and timing, and the fields are *exactly* that closed set. A
    denylist of banned names (the first cut) passed the first person-shaped field
    nobody thought to ban — `recipient="R07"` sailed through. An allowlist passes
    only what is enumerated, so a subject cannot enter unnoticed. reference.py
    enforces the same at import as a build failure; this is its test face."""
    assert set(ScheduledDose.__dataclass_fields__) == {"vaccine", "dose", "recommended_age"}
    assert set(Schedule.__dataclass_fields__) == {"version", "as_of", "source", "doses"}


def test_the_import_guard_fires_on_a_drifted_field_set(monkeypatch):
    """The build-time guard, proven to have teeth (the house's plant-a-violation
    discipline). Point the allowlist at a subset and the check must raise — so a
    real field added to the dataclass, against a matching allowlist edit, is the
    only way past, which is the deliberate act the guard forces."""
    import homestead_health.reference as ref

    monkeypatch.setattr(ref, "_DOSE_FIELDS", frozenset({"vaccine"}))
    with pytest.raises(RuntimeError):
        ref._check_no_subject_can_enter()


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
