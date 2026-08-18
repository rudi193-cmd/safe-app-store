# Homestead · Health

**Family health records the household holds itself.** Module three on
**Homestead · Affairs**, sibling to `homestead-law` and `homestead-ledger`,
incubating here toward promotion to `rudi193-cmd/homestead-health` — the
law-gazelle → homestead-law path, walked again.

The design is
[`homestead/docs/PLAN-homestead-health.md`](https://github.com/rudi193-cmd/homestead/blob/main/docs/PLAN-homestead-health.md):
the packs (immunizations first — one pack proves the seam), the rungs field by
field, the module invariants H-1…H-5, and the five bites.

**Status: every invariant the plan named (H-1–H-5) and the whole records track
(bites 1–5) are built and green — `UNBUILT` is empty.** What remains is the
2026-08-17 extension, still **proposed, not ratified**: the reference and living
lanes (bites 6–7). Bite 1 — **the
seat** — pins the engine and proves the pin. Bite 2 — **the roster**
(`homestead_health/roster.py`) — is subjects before records: opaque ids
(`subj-01`, minted by a counter, never derived from the person), the id →
person mapping stored through `homestead.keep`'s record layer and reached only
through the gate, a subject's name held at `L4` when the subject is a minor and
`L3` otherwise, and a `VisibleLog` line that carries the id and nothing of the
name (H-1). A subject survives a restart. Bite 3 — **the immunizations pack**
(`homestead_health/packs/immunizations.py`) — is health's first real schema,
classified at import in the custody pack's exact shape: the subject id (`L3`),
the vaccine (`L4`, a medical act on a person), dates that name nobody by
themselves (`L2`, while the record composes to `L4`), provider and source
(`L3`), and notes (`L4`); deleting one field's rung fails the build naming it
(H-4). Bite 4 — **due onto Today** (`homestead_health/due.py`) — computes the
next dose on **calendar** days (a booster interval does not skip weekends, so a
Saturday due date stays Saturday — not `court_days`) and renders the Today line
only when its count survives the engine's k ≥ 2 re-identification gate
(`cover_counts`, applied to the household's subjects): a two-child household
renders "2 immunizations due this month", a one-child household renders nothing,
from a **closed** operator-facing vocabulary that has no slot for advice (H-2).
Bite 5 — **the school form** (`homestead_health/school_form.py`) — is health's
first purposed egress: it serves a subject's several doses through `S4_EGRESS`
with a declared purpose (never reaching a `.payload`), composes them into one
form, and exports through `homestead.keep`'s export path — the artifact to
`exports/`, one `IntegrityLog` entry and one `VisibleLog` `EXPORTED` act carrying
references and no content (I-15), the head anchor held off the log's own tree and
returned to record off the machine, so a hand-edited entry fails
`verify(expected_head=…)`. **H-5 — the pinned reference snapshot**
(`homestead_health/reference.py`) — is the public CDC/ACIP immunization schedule
carried as a versioned, dated snapshot that names its own edition, holds **no
subject**, reads no clock, and dials for nothing (I-17): public reference the
operator pins and updates by a deliberate act, never a runtime fetch, and never
joined to a child (the H-2 wall). **H-3 — the emergency card**
(`homestead_health/emergency.py`) — is the one artifact whose purpose is to
leave: an **authored, never computed** field set (no `auto_include`, no
relevance heuristic) exported like any other record — usefulness does not lower
the rung, the ledger holds the act not the content — with only the operator's
chosen fields, a recorded gap for a chosen-but-empty one, and an `L5` field
dropped without a trace. Its subject-id guard is shared with the school form
(`_egress.py`), so the audit's egress fix protects both by construction.
Every H-* claim is now promoted to its own test file and
`tests/test_invariants_pending.py`'s `UNBUILT` is empty — the guard stays, ready
for the next claim the day its module is named. The
seat's own guarantees (the pin is true and capped, nothing imports the
network, nothing listens, no second path resolver, no shadowed test basename)
are live tests in `tests/test_invariants_seat.py`.

The records track was then **adversarially audited** (`verified_by ≠ author`)
and remediated — `docs/audits/bites-2-5-audit.md` records the findings and the
fixes (a subject-id egress leak, a k≥2 dedup leak, a package-wide `.payload`
chokepoint scan replacing a weak per-module one, and several theatre/robustness
gaps). Suite: **61 passed / 2 xfailed**.

```bash
pip install -e ".[dev]"
pytest -q          # bare, from a cold checkout. No out-of-band install step.
```

> `homestead-affairs` is a pinned dependency consumed only through
> `homestead.keep`'s public API. Do not modify it, propose changes to it, or
> generalize app logic into it. Upstream changes are issues on
> [`rudi193-cmd/homestead`](https://github.com/rudi193-cmd/homestead).

**Synthetic data only.** No real household's health records enter this app
before the export/log story (bite 5) is built and audited — the engine's own
rule, and this module handles exactly the material the rung model calls `L4`.

Apache-2.0, matching the engine.
