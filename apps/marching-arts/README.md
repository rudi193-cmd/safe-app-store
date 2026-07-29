# marching-arts

**Placeholder name.** The app has not been named yet; this directory is
descriptive so that renaming it costs one `git mv` and a catalog edit.

Authorization core for a marching-program platform — the thing a corps, a
drumline or a high-school band would run to hold roster, craft and schedule
information without any of it leaving the building.

This is **P1** of [`docs/BUILD_PLAN.md`][plan] in `rudi193-cmd/quick-stupids`:
storage and the authorization resolver. It ships nothing a user sees, and it is
first on purpose. Everything else depends on it — including the sync spine,
which is this same component wearing a different hat. A device receives only
what its holder may see, so the filter that decides a query is the filter that
decides a sync. Build it once.

[plan]: https://github.com/rudi193-cmd/quick-stupids/blob/claude/quick-task-mskd7h/docs/BUILD_PLAN.md

---

## The idea

> Every guarantee is a mechanism or it is a wish.

A constraint that is stated will be violated. A constraint that is structural
cannot be. So none of the promises below are enforced by discipline:

| Promise | Mechanism |
| --- | --- |
| Hidden rows never appear in a count | `COUNT(*)` runs in SQLite under the authorization predicate. A test traces the connection and fails if more than one statement reaches the table. |
| A fact always carries its source | `CHECK (length(trim(source)) > 0)` in migration 001. SQLite rejects the insert; no caller can forget. |
| Only a human seals a grant | `CHECK (state != 'sealed' OR sealed_by IS NOT NULL)`. A grant nobody signed is a grant the system invented, and the schema will not store one. |
| Refusal is invisible | A subject you may not see returns byte-identical results to a subject who does not exist. Tested as indistinguishability, not as absence. |
| Roles grant nothing on their own | Authorization comes only from a grant naming the principal individually. A director with every role sees no health band. |
| The core cannot reach the network | An AST walk over every module, plus a check that importing it pulls in no third-party package. |

## Bands

`L0 SELF · L1 ROSTER · L2 CRAFT · L3 ACCOMMODATION · L4 HEALTH · L5 SAFEGUARDING · L6 FAMILY`

Two of these behave differently from the rest, and both are decisions rather
than defaults:

**L3 and above: derive the instruction, do not forward the fact.** A section
leader is told *rotate this member out of the block every twenty minutes*. They
are not told why. The payload is replaced with `NULL` in the SELECT list, so the
underlying fact never leaves the database — the row is still visible and the
instruction still readable, because a leader does need to know there is an
instruction to follow.

**L5 is never served, to anyone, under any grant.** Safeguarding concerns are
routed to the people whose job it is to receive them. In every
leadership-implicating case on the public record, surfacing was external; an
intake here would digitise a broken path rather than repair it. A grant that
reaches L5 does not open it, because the deny applies to the union of the
allows.

## The precedence rule

The resolver compiles to exactly one predicate:

```
(allow₁ OR allow₂ OR …) AND NOT (deny₁ OR deny₂ OR …)
```

Denies negate the **union** of the allows. Drop the parentheses around the
joined denies and only the first term binds — the rest silently stop applying,
nothing raises, and every row they were meant to withhold becomes visible. That
is the single most likely way to rebuild the leak this app exists to prevent, so
it has its own regression test.

A principal with no allow rules gets `0`, not `1`. Fail closed.

## Layout

```
marching_arts/
  bands.py     the classification scale, and the two bands that behave differently
  rules.py     Rule, Effect, and the compiler. Knows nothing about people.
  policy.py    who may see what. The only file that decides anything.
  schema.py    migration 001 — band and source, present from the start
  store.py     authorized reads. There is no second path.
tests/
  test_gate.py        count · filter · sort · empty state
  test_provenance.py  the schema's own guarantees, and per-record resolution
  test_rules.py       precedence, tested directly
  test_no_egress.py   the AST walk
```

## Run it

```bash
python3 -m pytest tests -q      # 51 passed
python3 app.py                  # a walkthrough on synthetic data
```

Stdlib only. Python 3.10+. No install step, no server, no ports.

## Why Python, when the plan says browser

The browser host reimplements these rules against `sqlite-wasm` on OPFS. This
core is where the rules are *decided* and where the gate tests live, and it is
dependency-light and import-pure precisely so the port is a port rather than a
rewrite of a dependency tree. The differential-testing pattern from the acoustic
kernel applies: two implementations, one reference suite.

That is also the promotion bar — injected seams, own tests green, a manifest, an
import-pure core — so this build is shaped for extraction from the day it is
written.

## Status

Playground. Contested tier, not canonical, not promoted. Scoped to its own SOIL
collection (`marching_arts_*`) with no fleet-store writes.
