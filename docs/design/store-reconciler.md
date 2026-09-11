# The store reconciler — design

> Status: **design / spec only** (no implementation yet). A build packet follows.
> Seat: Vishwakarma (architect) · dispatch 6DA315A5 · verifier: willow.
> Clean-room: designed from the pattern below and this repo's own layout; no
> external source was read or copied.

## The gap this closes

The SAFE store keeps two accounts of what apps exist, and nothing continuously
diffs one against the other:

- **The declared set** — what the house *says* it has:
  - `.willow/store/catalog.json` (`apps[]`: `id`, `status`, `path`, `tier`,
    `majors`, and friends; the root `catalog.json` is a pointer to it);
  - `stores/<major>/stored/<app_id>.json` — the keeping records (`app_id`,
    `majors`, `relation`, `anchor`, `location`, `maker`, `lane`, `state`);
  - `stores/<major>/promoted/<app_id>.json` — the promotion records;
  - `stores/pending.json` — declared *absences*, each with a `reason` and
    `blocked_on` (absence is a value, not a gap).
- **The materialized set** — what is actually on disk: the `apps/<name>/`
  directories.

`tools/catalog_lint.py` already asserts these two agree, but only as a
**fail-closed pass/fail gate**: it prints errors and exits 1, and a human then
reads the errors and hand-fixes the tree. The README says as much — prose drifts
from `make list`, and the lint tells you *that* they disagree without producing a
per-entry verdict or moving anything toward agreement. The same declared-vs-disk
shape recurs in `almanac-data/scripts/propagate-engine.sh` (one template →
eleven verticals, `cmp -s` deciding what to copy). The proven pattern is a
**reconciler**: enumerate both sides, emit a verdict per entry, then apply
**additively** — the shape this doc specifies.

The reconciler does **not** replace `catalog_lint.py`. Lint stays the CI gate
that says *"these disagree, stop."* The reconciler is the organ that produces the
structured verdict and, on request, writes the additive fixes that make lint pass
again — and it exposes a `--check` mode that CI can run as an early drift signal.

## 1. The reconcile function

```
reconcile(declared, materialized) -> Report
```

### Inputs

Both inputs are produced by **injected enumerators**, not read inline — this is
the seam that lets the same core serve almanac-data (see §4), and it matches this
repo's own "seams injected" discipline (`promote_check.py`'s inversion gate;
`forge.trust` reused wholesale under rule 11).

- `declared: dict[key, DeclaredEntry]` — for the store, the union of catalog
  `apps[]`, keeping records, and promoted records, keyed by `app_id`. Entries in
  `stores/pending.json` are carried as **declared absences** and suppress the
  `missing`/`stale` verdicts for their keys (an absence with a recorded reason is
  not a drift).
- `materialized: dict[key, MaterializedEntry]` — for the store, the `apps/<dir>/`
  set, keyed by directory basename (rule 8: `app_id` = directory name).

### Output — one verdict per key

The union of declared and materialized keys is walked once; every key lands in
exactly one bucket:

| Verdict | Condition | Store meaning |
|---|---|---|
| `missing` | declared (with a resolvable-in-principle location) **and not** materialized | catalog/keeping record names a local `path` whose `apps/<path>/` is absent |
| `source_changed` | declared **and** materialized, fingerprints differ | the record's derivable facts no longer match the directory |
| `up_to_date` | declared **and** materialized, fingerprints equal | record and directory agree |
| `stale` | materialized **and not** declared, and not in `pending.json` | `apps/<dir>/` with no catalog entry, no keeping record, no pending entry |

A key named in `stores/pending.json` is reported as `declared_absent` (an
informational bucket), never `missing` or `stale`.

### How `source_changed` is detected — and why

The choice is **a content hash over a canonical fact-projection**, computed at
reconcile time. Not mtime, not version. Justified against what this repo actually
stores:

- **mtime is worthless here.** A git checkout stamps every file with the checkout
  time — every `apps/*` directory in a fresh worktree carries an identical
  timestamp. mtime cannot survive a clone, a worktree add, or CI, so it can never
  be a trustworthy change signal in this tree.
- **version is sparse and unenforced.** Only a handful of catalog entries carry a
  `version` (`utety-chat`, `bt-controller`, several of the marching apps); most do
  not, keeping records carry none, and nothing forces a bump on change. A field
  most entries lack cannot be the primitive.
- **A stored content hash of the app code would be a lie about what the store
  holds.** The store's own rule is explicit: *"the code is not duplicated, the
  record is what `stores/` stores."* The declared entry is **metadata about** the
  app, not a byte-copy of it — so hashing app *bytes* against a stored digest
  measures the wrong thing.

So the fingerprint is a hash of the **derivable facts** the two sides are
*supposed* to agree on — computed fresh on each side, never persisted:

- `fingerprint(declared_entry)` = canonical hash of `{app_id, tier, majors
  (sorted), status/state, path-basename}` as the record declares them.
- `fingerprint(materialized_entry)` = canonical hash of the *same shape* derived
  from disk: directory basename, `safe-app-manifest.json`'s `app_id`, and the
  majors/state the keeping record for that directory yields.

`source_changed` fires when these two projections diverge — e.g. catalog
`majors` ≠ keeping-record `majors`, `status` ≠ record `state`, or manifest
`app_id` ≠ directory name. These are exactly the disagreements `catalog_lint`
already enumerates; the reconciler reframes them from "error strings" into a
`source_changed` verdict carrying the specific diverging fields.

The fingerprint function is **injected** (`fingerprint_declared`,
`fingerprint_materialized`), so almanac-data can supply byte-identity
(`cmp -s`-equivalent) without changing the core (§4).

## 2. Apply semantics — idempotent, additive-only

`apply(report, *, allow_delete=False) -> ApplyResult`

- **Idempotent.** Running `apply` twice yields the same tree and the second run
  reports every key `up_to_date` / `noop`. Nothing about an apply depends on
  prior state beyond what is on disk.
- **Additive-only.** `apply` may *write* records/metadata that are missing and
  *rewrite* a `source_changed` entry's declared fields to match the derivable
  facts. It never removes a directory, a catalog entry, or a keeping record.
- **Nothing deleted without an explicit flag.** `stale` keys are **reported, not
  removed**, unless `--allow-delete` is passed. Even then, deletion is
  archive-not-delete per store rule 4: the default remedy a `stale` verdict
  suggests is *"add a keeping record / a `pending.json` entry / set status
  `archived`"*, never `rm`.
- **The store's asymmetry is honored.** A `missing` key means a record names code
  that is not on disk. `apply` **cannot synthesize code** from a metadata record —
  so `missing` keys are routed to the `skipped` bucket with reason
  `no_materializer` (or, if the path genuinely no longer exists, `path_gone`).
  `apply`'s write side operates on the **records** side only: for a `stale`
  directory it can additively write a `stores/pending.json` stub (reason
  required) or a keeping-record skeleton for a human to complete; for a
  `source_changed` entry it can additively realign the catalog's *generated*
  fields (`tier`, `majors`, `status`) to the keeping record, which is the one
  direction the store already treats as machine-owned.
- **The `skipped` bucket.** Any key `apply` declined to act on, with a reason:
  `path_gone` (declared path no longer exists), `no_materializer` (code cannot be
  conjured), `needs_human` (a stub was written but a field a machine must not
  invent — e.g. a `reason`, a `maker` — was left blank, or the directory was a
  declared path under an id/basename slip, or the divergence was an
  unfixable manifest problem), `would_delete` (`stale`, and `--allow-delete`
  not set). `skipped` is a first-class output, not a silent drop, so a
  partial apply is always fully accounted for.
- **The `_archived_apps/` convention.** When `--allow-delete` archives a
  `stale` directory, it moves `apps/<id>/` to `_archived_apps/<id>/` (never
  `rm`, per store rule 4) in the same repo root. This is a new location, so it
  is named here explicitly: `_archived_apps/` lives outside `apps/`, which is
  the only tree `catalog_lint.py`'s coverage check
  (`for app_dir in ... (REPO / "apps").iterdir()`) walks — so an archived
  directory never trips the "no catalog entry" gate lint already runs.
  Nothing needs to be added to lint for this to hold; the convention is safe
  *because* it sits outside the tree lint already covers, not because lint
  was extended to know about it.
- **Declared-by-path is not stale, even under an id/basename slip.** The
  declared set is keyed by catalog id; the materialized set is keyed by
  directory basename. Rule 8 says these should be equal, but when they are
  not — a catalog entry named `renamed-foo` whose `path` still points at
  `apps/foo` — the directory `apps/foo` is not `stale`: some catalog entry
  names it, just not under its own basename as the key. `apply` checks every
  `stale` key's basename against the set of basenames the declared side's
  `path` fields name, and refuses to archive or stub a match
  (`skipped: needs_human`), leaving the id/basename disagreement itself to
  `catalog_lint`'s existing rule-8 check to report.

`ApplyResult` = `{applied[], skipped[], noop[]}`, each entry carrying its key,
the verdict it came from, and the action taken or the reason it was not.

## 3. Where it plugs in

- **CLI:** `tools/store_reconcile.py`, sibling to `catalog_lint.py` and
  `readiness_drift.py`, same house conventions (`--json`, `--strict` accepted,
  fail-closed on an unreadable corpus). Modes:
  - `--check` (default) — enumerate, print verdicts, exit non-zero if any
    `missing`/`source_changed`/`stale` remains (the drift signal);
  - `--apply` — perform the additive apply, print `ApplyResult`;
  - `--allow-delete` — opt into archive-style removal of `stale` keys.
- **Make target:** `make reconcile` (check) and `make reconcile-apply`, mirroring
  the existing `make list` / lint muscle memory.
- **Relation to `promote_check.py`:** they are **inverse organs and must not be
  merged**.
  - `promote_check.py` is the **forward gate**: a candidate directory → gates →
    (on pass) a `stores/<major>/promoted/<app_id>.json` record. It moves one app
    *up a tier* and is fail-closed on the trust boundary (§0.2, sealed
    witness).
  - `store_reconcile.py` is the **audit/heal organ**: the whole declared set ×
    the whole disk → verdicts → additive realignment. It never promotes, never
    mints a promotion record, and never crosses the trust boundary
    `promote_check` guards.
  - They meet at one read-only seam: the reconciler *consumes* the promoted
    records `promote_check --record` writes (a promoted app is `declared` via its
    promoted record), and it may **flag** — never fix — a promoted record whose
    `app_id` no longer resolves. Reconcile treats `stores/**` as authoritative
    input the same way `catalog_lint` does; it does not rewrite a witnessed
    promotion record, because that record is a signed decision, not generated
    state.
- **Relation to `catalog_lint.py`:** the reconciler is an **early signal ahead
  of the catalog_lint hard gate, not a replacement for it**. `--check` covers
  {id, tier, majors, majors-order, status, manifest presence/validity, pending
  reason/blocked_on} — the same fields the canonical fact-projection (§1)
  carries. It does **not** mirror every check catalog_lint makes; the
  following are deferred (a fleet gap tracks full parity):
  - keeping-record location resolves
  - multi-major requires relation
  - anchor-in-majors
  - valid state enum
  - duplicate id
  - empty majors

  lint stays the CI gate (it is already wired into
  `.github/workflows/store-ci.yml` as the "Catalog gate"). Sequence in CI:
  `store_reconcile --check` (drift report, non-blocking or advisory) →
  `catalog_lint --strict` (the hard gate). A green tree has both agreeing, but
  a green `--check` alone does not guarantee `catalog_lint --strict` will also
  be green.

## 4. Shared primitive with almanac-data — **YES**

The reconcile **core** (enumerate both sides → per-key verdict → additive apply
with a `skipped` bucket) should be one shared module, not duplicated — because
everything that differs between the store and almanac-data is isolated to **two
injectable seams**, and nothing in the core is store-specific:

| Seam | SAFE store | almanac-data `propagate-engine.sh` |
|---|---|---|
| **Enumerators** (`declared`, `materialized`) | catalog + keeping/promoted records ↔ `apps/<dir>/` | `almanac-template/<ENGINE_PATHS>` ↔ each vertical's copy of that path |
| **Fingerprint / equality** | hash of the canonical fact-projection (§1) | byte identity — the `cmp -s "$src" "$dst"` it already does |
| **Materializer** (apply of `missing`) | record-side only; code → `skipped` (`no_materializer`) | `cp` the template file into the vertical (its existing `copy_file`) |
| **Override / exempt list** | `stores/pending.json` (declared absences) | `LOCAL_OVERRIDES` (files a vertical maintains by hand) |

The verdict vocabulary already lines up one-to-one with what the bash script
prints: `=` → `up_to_date`, `~ (would update)` / `+` → `source_changed` then
applied, a template file with no vertical copy → `missing`, and `o (local
override)` → the `pending.json`/`declared_absent` equivalent. `propagate-engine`
is a hand-rolled, store-agnostic instance of exactly this reconciler with the two
seams hardcoded to files.

**Recommendation:** build the reconcile core as a small, dependency-free module
(stdlib only, matching `promote_check.py` and `catalog_lint.py`) that takes the
two enumerators, the two fingerprint functions, a materializer, and an
exempt-set. Ship the store's seams in `tools/store_reconcile.py`. The eventual
re-home of the core is the shared-common package the repo already contemplates
(`docs/conventions/shared-common-package.md`); almanac-data then re-expresses
`propagate-engine.sh` as a thin caller of the same core rather than a second
implementation. Do **not** fold almanac's `cp` materializer into the store build
now — design the seam, prove it with the store, and let the build packet leave
almanac's adoption as a named follow-on so the core is shared, not prematurely
coupled.

## 5. Test matrix the build packet must satisfy

**Verdict classification (pure, no filesystem writes):**

1. declared-only, path resolvable in principle → `missing`.
2. materialized-only, not in `pending.json` → `stale`.
3. both present, projections equal → `up_to_date`.
4. both present, `majors` differ → `source_changed`, diff names `majors`.
5. both present, `status` ≠ keeping-record `state` → `source_changed`.
6. both present, manifest `app_id` ≠ directory basename → `source_changed`.
7. key in `stores/pending.json` with reason → `declared_absent`, never
   `missing`/`stale`.
8. promoted record present + directory present → `up_to_date` (promoted path).
9. empty declared and empty materialized → empty report, exit 0.

**Fingerprint honesty:**

10. two checkouts with different mtimes but identical facts → `up_to_date`
    (proves mtime is not consulted).
11. an entry with no `version` on either side still classifies correctly (proves
    version is not required).
12. changing app *code bytes* without changing the derivable facts → still
    `up_to_date` (proves the store fingerprint is facts, not code bytes).

**Apply — additive & idempotent:**

13. `apply` on a `stale` dir writes a `pending.json` stub / keeping-record
    skeleton; the directory and all existing records are byte-unchanged.
14. `apply` then `apply` again → second run all `noop`; tree byte-identical
    (idempotence).
15. `apply` on `source_changed` realigns only the catalog's generated fields;
    the keeping record and promoted records are untouched.
16. `apply` never deletes a `stale` key without `--allow-delete`; the key lands
    in `skipped` with reason `would_delete`.
17. `apply` on a `missing` key routes to `skipped` (`no_materializer` /
    `path_gone`); no code is fabricated.
18. a stub that needs a human-authored field (`reason`, `maker`) is written blank
    and reported `skipped: needs_human`, never invented.

**Fail-closed & CLI contract:**

19. unreadable/malformed `catalog.json` → exit non-zero, no writes (matches
    `catalog_lint`/`readiness_drift` fail-closed convention).
20. `--check` exits non-zero when any `missing`/`source_changed`/`stale` remains,
    zero when the tree is fully reconciled.
21. `--json` emits the full `Report` and `ApplyResult` shapes.
22. after a successful `--apply`, `catalog_lint.py --strict` passes on the same
    tree (the reconciler's job is to make the existing gate green).

**Shared-seam proof (guards §4):**

23. the reconcile core, driven by a **byte-identity** fingerprint and a **`cp`**
    materializer over two temp dirs, reproduces `propagate-engine.sh`'s
    `=`/`~`/`+`/override behavior — demonstrating the core is store-agnostic and
    the two seams are the only variation.

---

ΔΣ=42
