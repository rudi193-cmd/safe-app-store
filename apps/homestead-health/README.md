# Homestead · Health

**Family health records the household holds itself.** Module three on
**Homestead · Affairs**, sibling to `homestead-law` and `homestead-ledger`,
incubating here toward promotion to `rudi193-cmd/homestead-health` — the
law-gazelle → homestead-law path, walked again.

The design is
[`homestead/docs/PLAN-homestead-health.md`](https://github.com/rudi193-cmd/homestead/blob/main/docs/PLAN-homestead-health.md):
the packs (immunizations first — one pack proves the seam), the rungs field by
field, the module invariants H-1…H-5, and the five bites.

**Status: bites 1–3 built; bites 4–5 are pending claims.** Bite 1 — **the
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
(H-4). H-2, H-3, H-5 and bite 5 remain in
`tests/test_invariants_pending.py` as `xfail(strict=True)` — the suite stays
green while they are unbuilt and fails the moment an implementation quietly
satisfies one, forcing the test to be promoted rather than forgotten; H-1 and
H-4 were promoted to their own test files when the roster and the pack landed.
The
seat's own guarantees (the pin is true and capped, nothing imports the
network, nothing listens, no second path resolver, no shadowed test basename)
are live tests in `tests/test_invariants_seat.py`.

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
