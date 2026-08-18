"""Due onto Today — calendar days, and a count that survives re-identification.

Bite 4. Two things a records module owes the operator the moment there is a
deadline in it: the next dose computed on the *right* calendar, and a Today line
that says how much is due without saying *whose*. Both have a wrong answer the
house has already been bitten by, so both are built against it.

## The calendar is calendar days, not court days — and that is the check

`homestead.keep.dates` grew up on court time: `court_days`, FRCP 6(a) roll-forward,
weekends and federal holidays skipped. A booster interval is not a filing deadline.
A dose due eight weeks after the last one is due on that calendar day whether or not
it is a Saturday, and a health due date rolled forward by court rules is BUG-1's
cousin wearing a stethoscope — off by two days, silently, in the safe-looking
direction. So `next_due` adds a **calendar** interval (`timedelta`), and *"a
Saturday due date stays Saturday"* is the bite's own *done when*, held by a test that
also shows `court_days` would have moved it.

The parsing still goes through the engine (`parse_deadline`/`Deadline`), so a dose
date is read by the one strict parser and refused if it is ambiguous (BUG-1). Only
the *counting* is the app's, because only the app knows this count is not a court's.

## The Today line says how much, never whose — via the engine's own gate

The plan's worked example: a two-child household's Today renders **"2 immunizations
due this month"**; a one-child household renders **nothing**, because *"1
immunization due"* over one child names the child — I-31's k ≥ 2 check biting at
exactly the scale the cover decision said it would. And a two-child household with
only one due renders nothing either: a count of one lives in exactly one child, so
the number resolves to a person the instant it is read.

That check is **not rebuilt here.** It is `homestead.app.cover.cover_counts`, the
engine's re-identification arithmetic (rule 11 — the house already has it), applied
to the household's **subjects** rather than its matters. The math is identical: k ≥ 2
on the anonymity set (here, the roster of subjects) and k ≥ 2 on the count, with a
dropped count leaving *no key* — never a rendered zero. Passing subjects where the
cover passes matters is the same k-anonymity question one dimension over, and reusing
the gate means the one place the arithmetic lives is the one place it can be wrong.

## The app never advises care (H-2's structural half)

Every operator-facing line this module can produce is a member of `DERIVED`,
parameterised by a **count and nothing else**. There is no free-text position for a
recommendation to be phrased in — the same discipline as the closed `Event` enum
(R-7, F-4): if the vocabulary is closed, no code path can compose *"you should get
this booster"*, because there is no template that says it and no slot to write it in.
The behavioural half — that a subject's record and a reference answer never share a
surface — lands with the surfaces; this is the half that is structural, and it is
here.

Because the count is only ever *rendered* after it clears the k ≥ 2 gate, a rendered
count is always at least two, so the plural template is always the right one — the
gate makes the grammar correct as a side effect, and `derived_line` needs no singular
form to get right.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Iterable

from homestead.app.cover import cover_counts
from homestead.keep.dates import Deadline, parse_deadline

__all__ = ["DERIVED", "derived_line", "next_due", "due_this_month", "today_line"]

#: The closed vocabulary of the Today line. Templates parameterised by `{n}` — a
#: count and nothing else. A recommendation cannot be phrased because no member says
#: one and there is no slot for one (H-2, R-7's shape). One template today; the set
#: is the point, not its size — a second is added here, never composed at a call
#: site.
DERIVED: tuple[str, ...] = ("{n} immunizations due this month",)


def derived_line(*, due: int) -> str:
    """The Today line for a count that has already cleared the gate.

    Returns a member of `DERIVED` formatted with the count — the whole of what this
    module will ever say to the operator about what is due. It is a pure renderer of
    the closed vocabulary: hand it the count, get the one line back. It does not
    itself apply the re-identification check (`today_line` does), so a caller that
    reaches it with an ungated count gets a line — which is why the gate is a
    separate function the surface is meant to call, and this one is the vocabulary it
    draws from.
    """
    if isinstance(due, bool) or not isinstance(due, int):
        raise TypeError(f"a due count is an int, not {type(due).__name__}")
    return DERIVED[0].format(n=due)


def next_due(dose_date: object, *, interval_days: int, today: object = None) -> Deadline:
    """The next dose's due date — a **calendar** interval after the last dose.

    Parsed through the engine's one strict parser, so an ambiguous dose date is
    refused rather than guessed (BUG-1); counted with `timedelta`, so the result is
    the calendar day `interval_days` later, weekend or not. This is deliberately
    *not* `court_days`: a booster interval does not skip Saturdays, and rolling a
    health due date forward by court rules would move it two days in the
    safe-looking direction with nothing to show for it.

    `today` fixes the reckoning day of the returned `Deadline` for determinism, the
    same way `parse_deadline` does; `None` reckons against the machine clock.
    """
    if isinstance(interval_days, bool) or not isinstance(interval_days, int):
        raise TypeError(f"interval_days is an int, not {type(interval_days).__name__}")
    if interval_days < 0:
        raise ValueError("a dose interval does not run backwards")
    base = _to_date(dose_date)
    reference = _to_date(today) if today is not None else None
    return Deadline(base + timedelta(days=interval_days), reference)


def due_this_month(deadlines: Iterable[Deadline], *, today: object) -> int:
    """How many deadlines fall in the current calendar month.

    *"This month"* is the calendar month of `today` — a plain year/month match, not a
    thirty-day window, because the line says "this month" and means the one on the
    wall. Overdue deadlines from an earlier month are not "due this month"; a due
    date next month is not either. This is the count `today_line` gates — computed
    here so the arithmetic is one place, then handed to the re-identification check
    before a single digit of it is rendered.
    """
    ref = _to_date(today)
    total = 0
    for d in deadlines:
        day = d.date if isinstance(d, Deadline) else _to_date(d)
        if day.year == ref.year and day.month == ref.month:
            total += 1
    return total


def today_line(subjects: Iterable[object], *, due: int) -> str | None:
    """The Today line the resting surface may show — or `None`, shown as nothing.

    `subjects` is the household's roster (ids or refs); it is the anonymity set the
    count must not resolve to. The count is passed through the engine's
    `cover_counts` — k ≥ 2 on the subjects and k ≥ 2 on the count — and rendered only
    if it survives. A one-subject household, or a count of one, drops to `None`, and
    the surface draws nothing (never a zero). A survivor is rendered as its real
    number through the closed vocabulary.
    """
    roster = [str(s) for s in subjects]
    shown = cover_counts(roster, due=due)
    count = shown.get("due")
    if count is None:
        return None
    return derived_line(due=count)


def _to_date(value: object) -> date:
    """A calendar `date` from a `Deadline`, a `date`, or a string the engine parses.

    A `datetime` is refused rather than truncated — it carries a time this module has
    no field for, and accepting it would let an instant sit where a calendar day
    belongs (the engine's own rule for the same reason)."""
    if isinstance(value, Deadline):
        return value.date
    if isinstance(value, datetime):
        raise TypeError("a dose date is a calendar day, not an instant")
    if isinstance(value, date):
        return value
    return parse_deadline(value).date
