# Bites 2–5 audit — the records track, attacked and remediated

**Audited 2026-08-18**, same session the four bites landed, by three
independent adversarial passes (`verified_by ≠ author` — none wrote the
implementation). Each ran real probes against the live modules and the pinned
engine, planted counterexamples, and mutation-tested the guards. Their brief
was to find *enforcement theatre* — a check or test that passes without
enforcing what it claims — the same failure mode the bite-1 audit found in the
seat's path scan.

**Verdict as delivered:** the core mechanisms held (subject opacity, the
gate/ledger/tamper chain, the build-failure classification, calendar
arithmetic), but the passes found **one critical edge, one severe leak, and a
cluster of theatre/robustness gaps**. All are remediated; findings and
dispositions below. Suite after remediation: **61 passed / 2 xfailed** (was
54 / 3 before the audit added tests and the two remaining xfails are the
genuinely-unbuilt H-3 and H-5).

## Critical

### C1 · A malformed subject id wrote the artifact and the ledger, then raised — a leak that looks like a refusal — **fixed**

The engine holds two independently-written "reference component" validators
that disagree: `keep/export._segment` accepts an embedded newline,
`keep/logs._ref` rejects it. Because `export_record` writes the artifact and
commits the `IntegrityLog` entry *before* it touches the `VisibleLog`, a
subject id such as `"subj-01\nFORGED"` passed through `export_history` left the
record on disk **and** in the tamper-evident ledger, then raised `ValueError`
when the visible log refused it — so the caller saw a failure while the record
had already left, and the two logs disagreed about whether the act happened.

The root cause is in the pinned engine (out of scope to change from here; worth
an upstream issue), but it is reachable through `school_form.py`, which passed
`str(subject)` on with only an emptiness check. **Remediation:**
`_validate_subject` now rejects — before a single dose is served — any id with a
separator, a `..`, or any control/format/whitespace character (newline, tab,
zero-width space; `str.isspace()` misses the last, so the Unicode category is
checked too), and refuses `None` rather than stringifying it to the
collision-prone literal `"None"`. A test asserts the newline id refuses with
`ExportRefused` and leaves **no** artifact and **no** log behind.

## Severe

### S1 · The k≥2 re-identification gate counted list length, not distinct people — **fixed**

`today_line` passed the household roster to the engine's `cover_counts` without
deduplicating, and `cover_counts` gates on `len()`. The natural caller shape,
`[dose.subject for dose in due_doses]`, repeats a subject whenever one child has
more than one dose due — so `today_line(["subj-01", "subj-01"], due=5)` returned
`"5 immunizations due this month"`: a **one-child household rendering a count**
that resolves straight to that child, the exact leak the gate exists to prevent.
No caller existed yet, so nothing had leaked, but it was a landmine for the
surface bite. **Remediation:** `today_line` dedupes to the set of distinct ids
before gating; tests pin that repeats of one child render nothing while two
distinct children still render.

## Theatre and robustness

### T1 · The `.payload` chokepoint was enforced by a weak, spelling-only, per-module scan — and not at all for `school_form` — **fixed**

The roster carried a per-module test matching the literal attribute `.payload`;
it would have missed `getattr(r, "payload")`, `vars(r)["payload"]`, and
`r.__dict__["payload"]` — the exact shape the engine's chokepoint history warns
about. `school_form.py` had no scan at all, and the engine's own chokepoint test
never walks this app. **Remediation:** the weak per-module scan is removed and
replaced by `tests/test_invariants_chokepoint.py`, one package-wide AST scan
that flags all four reach spellings across every module (homestead-health has no
gate and no store, so *none* may reach a payload), plus a self-test that the scan
catches each bypass — so a future weakened copy fails its own suite.

### T2 · `test_a_survived_subject_still_serves_only_through_the_gate` claimed a check it never ran — **fixed**

Its docstring said it checked "a resumed adult name (L3) renders on the list
while a resumed minor name (L4) derives," but the body only added a minor and
only asserted the derive. **Remediation:** split into
`test_a_minor_derives_but_an_adult_renders_on_the_household_list` (both cases
added and asserted, live) and `test_the_serving_mode_survives_a_restart` (both
dispositions asserted after a restart). The behaviour is deliberate and
plan-grounded — the plan declares roster names L4 *where the subject is a minor*,
so adults are L3 and render on the household's own list the way custody's
`opposing_party` does; H-1's opacity is the subject *dimension*, not a claim that
every name is withheld — and it is now tested, not merely asserted in prose.

### T3 · `Roster.add()` mutated in-memory state before the fallible store write — **fixed**

`self._names[sid] = record` ran before `store.put()`, so a losing writer on an
I-9 collision (two rosters over one store) kept one person's name on another's id
in memory against the record on disk. **Remediation:** the durable write and the
log act now happen before any in-memory mutation; a refused write leaves the
roster exactly as it was.

### T4 · `is_minor()` folded a corrupted rung into "adult" — fail-open — **fixed**

A record whose stored rung did not survive (corruption) reads `L5`, and
`is_minor` returned `False` for it — the same answer as a real adult, the
fail-*open* direction for the one attribute a future safety branch would read.
**Remediation:** `is_minor` returns `True`/`False` only for `L4`/`L3` and
*raises* for anything else — minority is undetermined for a record whose rung did
not survive, and it refuses to guess. The name itself still fails closed to
nothing on `serve` (a separate guarantee, kept).

### T5 · `next_due` dropped a `Deadline` dose-date's own reference — **fixed**

Unlike the engine's `court_days`, `next_due` honoured only an explicit `today=`
and silently fell back to the machine clock when handed a `Deadline` that already
carried a fixed reckoning day, breaking determinism. **Remediation:** it now
carries a `Deadline` dose-date's `.reference` through when no explicit `today=` is
given, matching the engine's convention; a test pins it.

### T6 · The `due_this_month` year check and the export log check were untested / coincidental — **fixed**

A mutant of `due_this_month` with the year clause removed still passed the suite
(no test varied the year); the export log test grepped only two hardcoded
literals. **Remediation:** a year-varying test pins that a September date from a
different year is not "due this month"; the export log test now asserts each log
entry's key set is a fixed closed set — a new field of any kind fails it, rather
than only the two literals the grep happened to know.

## Minor

- **The advisory-content-matcher promise in the immunizations pack** was written
  present-tense ("is caught") though the matcher is not yet wired into this app
  (no detail-pane surface hosts it). Softened to name it the *intended* guard and
  a debt for the detail-pane bite, matching custody's framing. (Not a bite-3/4
  defect — flagged so it is not forgotten when the surface ships.)
- **A same-microsecond export collision** surfaced a raw `FileExistsError`
  instead of the module's `ExportRefused` contract. Now converted at the boundary
  (the collision precedes any ledger write, so nothing is left half-committed).
- **A decorative assertion** (`None != derived_line(due=0)`) and an
  **over-promising `DERIVED` comment** were trimmed to say only what they hold.

## What held under attack (confirmed, not merely claimed)

- **Content never reaches a log.** Adversarial vaccine names (unicode, JSON-shaped,
  colliding with structural tokens) could not be driven into either log; dose
  content structurally has no path into a log write.
- **The tamper chain is solid.** `verify(expected_head=…)` caught reordering,
  truncation, and an anchor-matched forged append; the documented honest limit
  (both log and on-disk anchor edited together) behaves exactly as stated.
- **The build-failure classification is real.** An auditor exec'd a mutated copy
  of the *actual* `immunizations.py` source (one rung → `None`) and confirmed it
  dies at import naming the field; the rung table is defensible field-by-field
  against the five-step procedure.
- **Saturday stays Saturday, generally** — 57 Saturdays across a year swept and
  mutation-tested (swapping in `court_days` breaks the guard).
- **Subject ids are name-independent and restart-durable**, including a real
  separate-process write/read and adversarial names up to 5000 chars.
