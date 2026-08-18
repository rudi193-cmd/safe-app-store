"""H-2 — the app never advises care; and Due onto Today (bite 4).

Promoted out of `test_invariants_pending.py` when `homestead_health.due` landed,
the module's third promotion. The `test_h2_…` body is kept as written; around it
are the bite's two *done when* checks (`homestead/docs/PLAN-homestead-health.md`
§ bite 4):

* **a Saturday due date stays Saturday** — `next_due` counts calendar days, not
  court days, so a booster interval that lands on a weekend lands on the weekend;
* **a one-child household renders no count while a two-child household renders "2
  due"** — the Today line is gated by the engine's own re-identification check
  (`cover_counts`, k ≥ 2), applied to the household's subjects.

The structural half of H-2 is that the operator-facing vocabulary is closed
(`DERIVED`), so no code path can phrase a recommendation. The behavioural half —
a subject's record and a reference answer never sharing a surface — is the
surfaces' to hold, not this module's.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from homestead.keep.dates import Deadline, court_days

from homestead_health.due import (
    DERIVED,
    derived_line,
    due_this_month,
    next_due,
    today_line,
)


# ── H-2, promoted verbatim ───────────────────────────────────────────────────


def test_h2_derived_lines_come_from_a_closed_vocabulary():
    # Every line `derived_line` can produce is a member of the closed set,
    # parameterised by counts and nothing else — there is no free-text
    # position for advice to be phrased in, which is the structural half of
    # "the app never advises care". The behavioural half lands with the
    # surface itself.
    line = derived_line(due=2)
    assert line in {template.format(n=2) for template in DERIVED}


def test_the_vocabulary_is_closed_and_takes_only_a_count():
    """Whatever count it is handed, `derived_line` returns a member of `DERIVED`
    formatted — never anything composed. And every template's only placeholder is
    `{n}`: a template with a free-text field would be a slot advice could enter
    through, which is exactly what a closed vocabulary forecloses (R-7)."""
    import string

    for n in (2, 3, 7, 40):
        assert derived_line(due=n) in {t.format(n=n) for t in DERIVED}
    for template in DERIVED:
        fields = {name for _, name, _, _ in string.Formatter().parse(template) if name is not None}
        assert fields <= {"n"}, f"{template!r} has a field beyond the count: {fields}"


def test_derived_line_refuses_a_non_count():
    """A bool is an int subclass and nonsense as a count; it is refused before it
    can read as a rung-shaped truth (I-14's shape)."""
    with pytest.raises(TypeError):
        derived_line(due=True)


# ── the calendar is calendar days, not court days ────────────────────────────


def test_a_saturday_due_date_stays_saturday():
    """The bite's first *done when*. 2026-08-15 plus a 21-day interval is Saturday
    2026-09-05, and it stays there — `next_due` adds calendar days and does not roll
    a weekend forward."""
    result = next_due("2026-08-15", interval_days=21)
    assert result.date == date(2026, 9, 5)
    assert result.date.weekday() == 5, "Saturday — and it must remain Saturday"
    assert result.date == date(2026, 8, 15) + timedelta(days=21)


def test_next_due_is_calendar_not_court_days():
    """The same inputs through the court-day counter land somewhere else and never
    on a weekend — which is precisely why a health interval must not use it. The
    contrast is the proof that the calendar choice was deliberate, not incidental."""
    calendar = next_due("2026-08-15", interval_days=21)
    court = court_days("2026-08-15", 21)
    assert calendar.date != court.date
    assert court.date.weekday() < 5, "court_days never lands on a weekend; a booster does"


def test_next_due_reckons_against_a_given_today():
    """`today` fixes the returned deadline's reckoning for determinism, the engine's
    `parse_deadline` posture — the same interval read from two different 'today's
    has the same due date but a different days_until."""
    d = next_due("2026-08-15", interval_days=21, today="2026-08-20")
    assert d.date == date(2026, 9, 5)
    assert d.days_until == (date(2026, 9, 5) - date(2026, 8, 20)).days


def test_next_due_refuses_a_backward_interval_and_an_instant():
    with pytest.raises(ValueError):
        next_due("2026-08-15", interval_days=-7)
    with pytest.raises(TypeError):
        next_due(datetime(2026, 8, 15, 9, 0), interval_days=7)


# ── the Today line says how much, never whose ────────────────────────────────


def test_a_two_child_household_renders_the_count():
    """The plan's worked line, exactly: two subjects, two due → '2 immunizations due
    this month'. The number survives the k ≥ 2 gate on both the subjects and the
    count, and is rendered as itself through the closed vocabulary."""
    line = today_line(["subj-01", "subj-02"], due=2)
    assert line == "2 immunizations due this month"


def test_a_one_child_household_renders_nothing():
    """The plan's other half. With one subject the household *is* that child, so
    every count — 1 or 5 — is a fact about them, and the line is drawn as nothing
    (I-31, the k ≥ 2 gate on the anonymity set)."""
    assert today_line(["subj-01"], due=1) is None
    assert today_line(["subj-01"], due=5) is None


def test_a_count_of_one_resolves_to_a_child_even_in_a_larger_household():
    """k ≥ 2 on the count, not only on the subjects: one item lives in exactly one
    child, so '1 due' resolves to that child however many children there are."""
    assert today_line(["subj-01", "subj-02", "subj-03"], due=1) is None


def test_a_dropped_count_is_absence_never_zero():
    """A count that does not survive is drawn as nothing — never '0 immunizations
    due'. `today_line` returns None, and None is absence; a zero would be a fact
    about the household the gate exists to withhold."""
    dropped = today_line(["subj-01"], due=3)
    assert dropped is None
    assert dropped != derived_line(due=0)


def test_the_gate_is_the_engines_not_a_reimplementation():
    """The re-identification arithmetic is `cover_counts`, reused — the same numbers
    the cover would show for matters, here for subjects. A survivor is the real
    count; a two-subject household with four due renders four."""
    assert today_line(["subj-01", "subj-02"], due=4) == "4 immunizations due this month"


# ── due-this-month counts the calendar month ─────────────────────────────────


def test_due_this_month_counts_the_calendar_month_not_a_window():
    """'This month' is the month on the wall — a year/month match against today, not
    a thirty-day window. A due date in a later month is not this month's, and an
    overdue one from an earlier month is not either."""
    today = date(2026, 9, 10)
    deadlines = [
        Deadline(date(2026, 9, 1)),    # this month, already past in-month — still Sept
        Deadline(date(2026, 9, 30)),   # this month
        Deadline(date(2026, 10, 2)),   # next month — not counted
        Deadline(date(2026, 8, 28)),   # last month — not counted
    ]
    assert due_this_month(deadlines, today=today) == 2


def test_due_this_month_feeds_the_gate_end_to_end():
    """The pipeline the surface will run: count what is due this month, then gate it
    by the subjects before a digit is shown. Two subjects and two September due
    dates render the line; the same two dates in a one-subject household render
    nothing."""
    today = date(2026, 9, 10)
    deadlines = [Deadline(date(2026, 9, 5)), Deadline(date(2026, 9, 20))]
    count = due_this_month(deadlines, today=today)
    assert today_line(["subj-01", "subj-02"], due=count) == "2 immunizations due this month"
    assert today_line(["subj-01"], due=count) is None
