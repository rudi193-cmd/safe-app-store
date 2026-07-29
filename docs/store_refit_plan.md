# The store refit — a storehouse, not a shelf

b17: SAPS1

**A store is a stock laid up, and the building that keeps it.** From
`instaurare`: to establish, and to renew. Not a place that sells — a place that
*keeps*. [`stores/README.md`](../stores/README.md) already says this in prose,
and [`CLAUDE.md`](../CLAUDE.md) opens by refusing the shop. The refit is what
happens when the mechanisms are held to the same definition the prose already
took.

> Every guarantee is a mechanism or it is a wish.

The reframe was ratified in **PR #88** (`claude/store-reframe-law`, merged
2026-07-24), which landed the two-tier law and the fail-closed promotion gate,
and said plainly in its own *Out of scope*: *"Existing `apps/` are not migrated,
and no app is retro-fitted."* This is that migration. It is a refit rather than
a build because the structure already exists — it is simply empty, and the
thing actually doing the work is still shaped like a shop.

---

## What is true today

Measured, not recalled. Every row is reproducible from a clean checkout.

| Claim in the prose | What the mechanism does | Evidence |
| --- | --- | --- |
| A store per major, holding work at two tiers | **12 tier directories, all empty.** `stores/{cpp,go,node,obsidian,python,rust}/{stored,promoted}/` contain nothing but `.gitkeep` | `find stores/*/stored stores/*/promoted -type f ! -name .gitkeep` → **0** |
| The store keeps work-in-becoming | **All 27 builds live in flat `apps/`**, with no major, no tier, no keeping record | `ls -d apps/*/` → 27; 26 carry a manifest (`llmphysics` has none) |
| Promotion is *recorded* under `stores/{major}/promoted/` (rule 8) | `promote_check.py` prints a verdict and **writes nothing**. Nestor and Jeles both passed all 8 gates in #88; neither left a record | `stores/promote_check.py:276-286` — returns an exit code, no write path |
| The catalog is a status map, *not a shelf* (rule 9) | `status` ∈ `stable · beta · coming_soon · archived` — **readiness-to-buy**, not state-of-becoming. `tags` is a browse taxonomy. There is **no `tier` field and no `major` field** | `catalog.json`, 30 entries, keys: `author · canonical · description · id · name · path · repository · status · tags · version` |
| The catalog lives in `.willow/store/` (rule 9) | It lives at the **repo root**. `.willow/` holds only `project.json` | `ls .willow/` |
| — | `discovery_sources` carries **public.tools** — a directory of other people's hosted tools, *"mine for catalog ideas, gap-spotting"* | `catalog.json:406` |

The pattern: **`stores/` is scaffolding that keeps nothing, and `catalog.json`
is a shop that does all the work.** The provision-house was declared and then
never moved into.

### The collision that has to be settled first

The two governing documents name the lower tier differently, and put it in
different places:

| Document | Lower tier is called | And lives at |
| --- | --- | --- |
| `CLAUDE.md` §5 | **the playground** — a contested commons, untrusted by default | `apps/` |
| `stores/README.md` | **Stored** — provisional, incubating, a held piece | `stores/{major}/stored/` |

Same tier. Two names, two locations, and no mechanism reconciling them —
which is precisely why one of them is empty. Nothing downstream can be built
honestly until this is one thing.

**The resolution this plan takes:** `apps/` is the *working surface* — where a
maker's code actually sits while it is contested. `stores/{major}/stored/` is
the *keeping record* — what the house knows it is holding. A storehouse keeps a
ledger of its stock; it does not keep two copies of the stock. **The code is
not duplicated. The record is what `stores/` stores.**

This also settles the Almanac, which is already correct and should be read as
the worked precedent: [`stores/almanac/`](../stores/almanac/) holds no tiers
because *"the store does not store it"* — it is a pointer to a live feed. A
record that points is a record; a frozen copy is rot. Same mechanic, applied to
builds.

---

## The refit

Sequenced by dependency. Each phase ships the gate that makes its promise
checkable — **a phase without a gate is not done.**

### P0 — Settle the tier vocabulary · unblocked

One name per tier, in both documents, with the collision above resolved
explicitly rather than quietly. `stores/README.md` adopts *playground* for the
contested tier and states that `stores/{major}/stored/` holds **records of what
is held**, not held code. `CLAUDE.md` §8 gains the same sentence so the law and
the map agree.

Nothing is moved. This is the phase that makes the next four unambiguous, and
it is deliberately separate so the vocabulary change is reviewable on its own.

**Gate.** A doc test asserting the two files use one vocabulary: no occurrence
of `stored/` as a *code location* in either, and the tier names match a single
canonical list. Cheap, and it stops the collision reopening.

### P1 — The keeping record · needs P0

Every held build gets exactly one record at
`stores/{major}/stored/<app_id>.json`:

- `app_id`, `major`, and **where the code actually is** — an `apps/` path, or a
  loose repo URL for work kept outside this tree
- `maker` — attribution, per §7; ideally the signed manifest
- `lane` — the app's `store_scope`, so the record states the app's reach rather
  than leaving it to be discovered
- `state` — where it is in its becoming, not its readiness to be bought

This is the phase that makes `stores/` a storehouse: after it, the twelve empty
directories hold the house's actual knowledge of its stock, and the majors mean
something because each build is assigned to one.

`llmphysics` is the first thing the record surfaces — a build directory with no
manifest at all. It gets a record like everything else; the record is allowed to
say the manifest is missing. **Absence is a value, not a gap** — the same
mechanic `dci_scores.db` uses for the unscored 2021 season, and Nestor for
*pending*.

**Gate.** Extend `tools/catalog_lint.py --strict`: every build directory on disk
resolves to exactly one keeping record; every record resolves to a real location;
no build appears under two majors. Fail-closed, wired into the existing `gates`
job.

### P2 — Promotion leaves a record · needs P1

`promote_check.py` gains `--record`, and on a PASS writes
`stores/{major}/promoted/<app_id>.json`: the verdict, the eight gate results
individually, the promoted repo URL, and `verified_by`.

The witness requirement becomes mechanical rather than attested prose:
**`verified_by == author` refuses to write.** §0.2 — proposing and ratifying
never rest in the same hand — is currently enforced by a person remembering it.

Re-run against Nestor and Jeles to mint the first two real records. They already
passed all eight gates in #88; this phase is what makes that passage *leave a
mark* instead of scrolling past in a terminal.

**Gate.** A test that a PASS with `verified_by == author` writes nothing and
exits non-zero, and that a `--record` run on a candidate that fails any gate
leaves the directory untouched. Fail-closed on both edges.

### P3 — The catalog becomes an index · needs P1, P2

Today `catalog.json` is authored by hand, which is why it drifts — issues #78
through #82 are all catalog-vs-reality drift, filed against a file whose only
source of truth is whoever edited it last.

After P1 and P2 the records *are* the truth, so the catalog is **generated**
from them and stops being authorable:

- `tier` and `major` become real fields, because there is now something to read
  them from
- `status` splits: shop vocabulary (`stable`, `beta`, `coming_soon`) gives way
  to state-of-becoming; **`archived` stays** — §4, archive never delete
- it moves to `.willow/store/` per §9, with a root pointer left for existing
  consumers (`tui.py`, `store_mcp.py`) so nothing breaks on the move

**Gate.** `catalog_lint --strict` regenerates and diffs: a catalog that differs
from what the records produce fails CI. After this the catalog **cannot** drift,
because nobody writes it. That closes #78–#82 structurally rather than one
correction at a time.

### P4 — Discovery is not the house's job · independent

`discovery_sources` is the last purely-market organ: a curated directory of
third-party hosted tools to mine for ideas. Nothing in it is kept, provisioned,
or promoted, and its own `caveats` field says it isn't SAFE and must not carry
sensitive data. It is research input, and it belongs in `docs/`.

**Gate.** The catalog schema rejects unknown top-level keys, so the shelf cannot
grow a new organ without someone deciding to add one.

---

## Not doing — and why that is the point

- **Not moving code into `stores/`.** A storehouse keeps a ledger of its stock,
  not a second copy of it. Duplicating 27 build trees to populate twelve
  directories would be the shop reflex wearing the storehouse's clothes, and the
  copies would drift within a week — exactly the failure issue #83 already
  documents at 17-of-17 for `safe_integration.py`.
- **Not migrating `apps/` layout.** The playground is the working surface and
  stays flat. `app_id = directory name` still holds while a build is contested
  (§10), because SAFE dev-fallback auth depends on it.
- **Not promoting anything.** The refit gives promotion a *record*. What clears
  the bar is a separate, witnessed decision per build, and it is not this
  document's to make.
- **Not touching the Almanac.** It is already right, and it is the precedent the
  keeping record is modelled on.
- **Not lane-scoping the 24 unscoped apps.** Real (only `marching-arts` and
  `field-acoustics`, both built after #88, declare `store_scope`), and it wants
  its own bite — nine apps read fleet collections through `libs/willow-read`,
  so a strict lane is a behavioural change, not a manifest edit. P1 *records*
  each app's lane, which is what makes that later bite scopable.

---

## Open gates

- **Which major does each build belong to?** 27 builds, mostly Python, but
  `utety-chat` is a web front, `field-acoustics` carries a TypeScript kernel
  beside a Python model, and `the-binder` is a Cloudflare Pages shell. A build
  that spans two crafts needs a rule — primary major, or a record that names
  both — and the answer changes P1's schema. **This blocks P1 and nothing else.**
- **`llmphysics` has no manifest.** Held, unmanifested, and in the catalog. The
  record can say so; whether it stays held or is archived (§4) is the operator's.
- **Loose repos.** `stores/README.md` admits work kept *"local, or a loose repo"*
  — outside this tree. `grove` points at `safe-app-grove`, which does not appear
  in the account's repo list. A keeping record for something the house cannot
  reach is a claim; decide whether unreachable means *archived* or *pending*.
- **Who witnesses?** P2 makes `verified_by ≠ author` mechanical, which is only
  meaningful if there is a second hand. Single-operator fleets have exactly the
  problem that auto-approve had in grove #29 — worth deciding deliberately
  rather than discovering when the first promotion is refused.

---

*The head of this house is the architect, not a shopkeeper.* `ΔΣ=42`
