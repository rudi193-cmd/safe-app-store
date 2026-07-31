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

### P0 — Settle the tier vocabulary · done

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

**Done 2026-07-31:** `stores/README.md`'s "Stored" tier renamed to
"Playground"; both files now state, verbatim, "The code is not duplicated. The
record is what `stores/` stores." — `tests/test_tier_vocabulary.py`, wired into
`store-ci.yml`'s `gates` job, is the gate. Verified it can fail: reverting
`stores/README.md` to its pre-P0 wording reddens all four assertions.

### P1 — The keeping record · needs P0

Every held build gets exactly one record at
`stores/{anchor}/stored/<app_id>.json`:

- `app_id`, `majors`, and **where the code actually is** — an `apps/` path, or a
  loose repo URL for work kept outside this tree
- `maker` — attribution, per §7; ideally the signed manifest
- `lane` — the app's `store_scope`, so the record states the app's reach rather
  than leaving it to be discovered
- `state` — where it is in its becoming, not its readiness to be bought

This is the phase that makes `stores/` a storehouse: after it, the twelve empty
directories hold the house's actual knowledge of its stock, and the majors mean
something because every build is accounted for under one.

`llmphysics` is the first thing the record surfaces — a build directory with no
manifest at all. It gets a record like everything else; the record is allowed to
say the manifest is missing. **Absence is a value, not a gap** — the same
mechanic `dci_scores.db` uses for the unscored 2021 season, and Nestor for
*pending*.

#### One record, more than one major

A build may span crafts, so `majors` is a list and the record carries the
**relation** between them — `differential-paired`, for two implementations of
one component held together by a differential suite. The relation is the
load-bearing fact: it is what makes two copies of a thing *safe* rather than the
drift hazard #83 measures at 17-of-17 for `safe_integration.py`. A record that
flattens a spanning build to a single major is losing precisely the thing worth
keeping.

The record still lives in one place, filed under the **anchor** major — *the
implementation that defines what correct means*, which for a differential pair
is the reference side, not the larger side. Anchor is not "primary": it is not a
judgment about which half matters more, and it is not decided by file count.

#### The `state` vocabulary is closed, and pinned here

`state` is a **closed enum, validated by the lint** — an unknown value fails,
exactly as `catalog_lint --strict` today rejects a `status` it does not know.
Proposed set, ratified in P0 alongside the tier vocabulary because it is the
same collision one level down:

`seeded · building · gated · stalled · archived`

Two distinctions the enum has to keep separate, because conflating them is the
mistake that has already been made once:

- **Tier is expressed by the path** (`stored/` vs `promoted/`), never by
  `state`. A build is not *in state* playground; playground is where it is kept.
- **Missing facts are recorded, not encoded as a state.** `llmphysics` is not
  `state: unmanifested` — it is whatever it actually is, with the absent
  manifest recorded as a gap. Otherwise every new kind of absence needs a new
  state value and the enum stops closing.

Pinning this in P1 rather than P3 is deliberate: after P3 the records are the
only writer, so an unpinned vocabulary stops being a documentation problem and
becomes data loss with no second source to check against.

**Gate.** Extend `tools/catalog_lint.py --strict`, fail-closed, wired into the
existing `gates` job:

- every build directory on disk resolves to **exactly one** keeping record, and
  no two records claim the same `app_id`
- every record resolves to a real location
- every major named on a record is a real store
- **a record naming more than one major must name the relation** — a spanning
  build with an unnamed relation fails
- `state` is in the closed set

**Done 2026-07-31, with two apps deliberately left open:**

- `tools/catalog_lint.py`'s `lint_records()` implements the gate above exactly
  (plus: a record's `anchor`, when named, must be one of its own `majors`).
  `tests/test_p1_keeping_records.py` proves each check can fail, against a
  synthetic repo, wired into `store-ci.yml`.
- `stores/browser/` was added as a seventh major — the gap
  `docs/store_refit_survey.md` named directly: forcing jarvis and
  `band-camp-arcade` (self-contained HTML/JS, no backend, no build step) into
  `node` would state something false about what craft they're built in.
- 27 of 29 `apps/` builds now have a record under `stores/{major}/stored/`.
  `llmphysics` got exactly the treatment this section anticipated: its
  wrong-dialect manifest (`safe-app-manifest.js`, per the survey) is recorded
  as a gap in its `notes`, not smoothed over.
- **`the-binder` and `utety-chat` are recorded in `stores/pending.json`
  instead**, each with the specific open question blocking it, per
  `docs/store_refit_survey.md`'s own "Open gates" section: both span crafts
  with no reference implementation defining correct, so `anchor` has no
  principled answer and the closed five-term relation vocabulary has no term
  for either shape. Inventing an anchor or forcing a relation would be
  exactly the kind of false record P1 exists to prevent. Resolving this needs
  a human call — either the relation vocabulary grows a term, or these two
  get a rule of their own — not an agent's guess while implementing the gate.
- `state` was assigned per app with a documented, mechanical-where-possible
  policy: `archived` mirrors `catalog.json`; `gated` means a real,
  CI-verified test suite exists (the `app-tests` matrix plus each dedicated
  workflow) — a claim about the gate, not about feature completeness (see
  `source-trail`'s and `vision-board`'s notes, where `state` and catalog
  `status` deliberately disagree); `stalled` cites a specific broken-entry-point
  or non-functional finding from one of the two survey docs; everything else
  defaults to `building`. Each record's `notes` cites its evidence.

### P2 — Promotion leaves a record · done, with the first real records deferred

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

**Done 2026-07-31, and the two real records are deferred, not minted:**

- `stores/promote_check.py` gains `--record`. On a candidate that clears every
  gate it writes `stores/{major}/promoted/<app_id>.json` carrying the verdict,
  the promoted `repo_url`, `author` and `verified_by`, the major with the
  reason it was chosen, and **every gate result individually**.
- **The gate emits nine results, not eight.** The paragraph above says "the
  eight gate results" and was written against #88; `vault_leak [M]` was added
  afterwards by box audit B13. The record serialises whatever `check()`
  returned rather than a fixed eight, so it cannot carry a stale invariant
  count — the same failure mode as quoting a test count from a README.
- **§0.2 is now a mechanism.** `record_promotion()` re-checks
  `verified_by ≠ author` itself instead of trusting the `witnessed [M]` gate it
  was handed. Deliberate duplication: if that gate is ever reordered, renamed
  or made skippable, the *record* still cannot be minted by one hand. Every
  refusal returns before the first filesystem call, so a denied run leaves
  `stores/` byte-identical — no partial file, no directory created and
  abandoned.
- **Which store it files under** is the attestation's `major` when declared,
  checked against the stores actually on disk (discovered, not hardcoded — the
  P0 review fix), and otherwise `python`. The default is mechanical rather than
  a preference: every gate a candidate can *pass* is Python-shaped (`ast.parse`
  over `*.py`, Python top-level imports, a `module:symbol` seam resolved to a
  `.py`, pytest), so on this gate PASS implies python. Reasoning is in
  `resolve_major()`'s docstring, where it stops being true the day
  promote_check grows a non-Python path.
- **An existing record is not overwritten.** A promoted record is a witnessed
  decision; silently replacing one destroys the evidence that it was ever made
  differently. Re-minting means removing the old record deliberately.
- **`app_id` is checked before it becomes a path.** Review on #133 caught that
  `att.get("app_id")` — an attested, external field — went straight into
  `stores_root / major / "promoted" / f"{app_id}.json"` with nothing rejecting
  something like `"../../../tmp/evil"`. `_APP_ID_PATTERN` now requires a plain
  identifier (no `/`, no `\`); without a separator there is no path component
  left to address a parent directory with, so a single check closes the whole
  class rather than needing a second resolve-and-compare pass — the reviewer's
  own suggested fix, not a broader one.
- `tests/test_promote_check_record.py` (19 tests) is the gate, wired into
  `store-ci.yml`'s Drift-guards step. **Verified it can fail:** six mutations
  of `promote_check.py`, each reverted after —
  dropping the `verified_by == author` refusal reddens 2 tests; dropping the
  all-gates-pass refusal reddens 4; creating the target directory *before* the
  checks (a partial write) reddens 7, every "untouched" assertion at once;
  overwriting an existing record reddens 1; accepting any declared major
  reddens 1; dropping the `app_id` shape check reddens the 2 path-traversal
  tests and nothing else.
- **Nestor and Jeles were not re-run, and no record was minted for either.**
  Neither extracted candidate directory exists in this repository, and neither
  is reachable from this environment — they are external, already-promoted
  repos (`grep -rl promotion.json` finds only `promote_check.py` itself and a
  `BUILD_PLAN.md` reference; there is no `promotion.json` anywhere on disk).
  Writing their records would have meant inventing the attestations they are
  supposed to be recording, which is precisely the falsehood the gate exists to
  refuse. **Absence is a value, not a gap** — same treatment `llmphysics`'s
  missing manifest got in P1. `stores/*/promoted/` therefore still holds only
  `.gitkeep`, and the first real minting is an operator's run against the real
  extractions: `python stores/promote_check.py <nestor-checkout> --record`.
  The mechanism is proven on synthetic candidates that clear all nine gates for
  real — real pytest subprocess, real vault-leak lint, real AST scans — not on
  stubs.

### P3 — The catalog becomes an index · needs P1, P2

Today `catalog.json` is authored by hand, which is why it drifts — issues #78
through #82 are all catalog-vs-reality drift, filed against a file whose only
source of truth is whoever edited it last.

After P1 and P2 the records *are* the truth, so the catalog is **generated**
from them and stops being authorable:

- `tier` and `major` become real fields, because there is now something to read
  them from
- `status` splits: shop vocabulary (`stable`, `beta`, `coming_soon`) gives way
  to the `state` enum pinned in P1; **`archived` stays** — §4, archive never
  delete. The lint's accepted set moves in the *same* change, because it
  currently rejects anything outside the four it knows — that is how an invented
  `status: "playground"` was caught, and the catch was cheap only because the
  lint already existed
- it moves to `.willow/store/` per §9, with a root pointer left for existing
  consumers (`tui.py`, `store_mcp.py`) so nothing breaks on the move

**Gate.** `catalog_lint --strict` regenerates and diffs: a catalog that differs
from what the records produce fails CI. After this the catalog **cannot** drift,
because nobody writes it. That closes #78–#82 structurally rather than one
correction at a time.

**Done 2026-07-31, with the `status` vocabulary migration deliberately not
included:**

- **`tier`, `majors`, and `state` are now real fields** on every non-archived
  catalog entry that has a `path`: 27 entries generated from their
  `stores/{major}/stored/` record (`tier: "playground"`, that record's
  `majors` and `state`, verbatim); 2 pending entries (`the-binder`,
  `utety-chat`) get `tier: "playground"` only, since there's no record to read
  `majors`/`state` from yet. No promoted entries exist in this catalog today,
  so the `tier: "promoted"` path is implemented and tested against synthetics
  but has never run against a real one — named here rather than left quiet,
  same treatment P2 gave the Nestor/Jeles deferral.
- **`tools/catalog_lint.py`'s `lint_generated_fields()`** is the gate: for
  every in-scope entry, `tier`/`majors`/`state` must equal what the matching
  keeping record (or promoted record, or pending entry) says. 12 unit tests
  against a synthetic repo, plus verified against the real one: temporarily
  set `field-acoustics`'s catalog `majors` to `["rust"]` (its record says
  `["python", "node"]`), watched `catalog_lint.py --strict` catch exactly that
  mismatch, restored it.
- **The catalog moved to `.willow/store/catalog.json`** per rule 9. The root
  `catalog.json` is now a pointer (`{"$pointer": ".willow/store/catalog.json"}`),
  not a second copy — `tools/catalog_lint.py`, `tui.py`, and the `Makefile`'s
  `list` target were the three real consumers (checked; `store_mcp.py` does
  not touch the path directly), all repointed. `tests/test_catalog_location.py`
  guards against the pointer growing back into a duplicate.
- **What this pass deliberately did *not* do: split `status`.** The plan's own
  wording — "shop vocabulary gives way to the `state` enum; `archived` stays"
  — would mean rewriting the value of a field every existing consumer already
  reads (`tui.py`'s status column, `catalog_lint.py`'s `VALID_STATUSES`, this
  repo's own README prose, and whatever a human currently means by "beta" in
  the shop sense). That is a consumer-facing vocabulary change in its own
  right, not a mechanical consequence of the records existing — the same
  reasoning P0 used to keep the tier-vocabulary fix "deliberately separate"
  and reviewable on its own. `tier`/`majors`/`state` are additive: nothing
  that read `status` before reads anything different now. Splitting `status`
  itself is a distinct next bite, not folded in here.
- **`grove` and `willow-grove` (loose external repos) still have no keeping
  record and get no generated fields**, same gap `docs/store_refit_plan.md`'s
  own "Open gates" section already named before this phase started — P3
  didn't resolve it, only confirmed it's still open and left both entries
  untouched rather than guessing at a record for a build the house cannot
  measure.

#### The `status` vocabulary migration — the bite P3 deliberately deferred · done 2026-07-31

Decided explicitly, not inferred: **full replacement.** `status`'s vocabulary
*is* the `state` enum now (`seeded · building · gated · stalled · archived`);
the old shop vocabulary (`stable`/`beta`/`coming_soon`) is gone, and so is the
separate `state` field P3 added — a stored entry's `status` carries that value
directly, with nothing left to duplicate it.

The real question this settled wasn't mechanical — it was whether collapsing
the two fields loses something worth keeping. `vision-board` is the concrete
case: catalog-`stable` (it works, people use it) but P1-`state: building` (no
CI-verified suite). Merging the fields means it now reads `status: building`
— true about its gate, not about whether a person should try it. Decided to
accept that trade rather than keep a second field alive to preserve a
distinction the plan's own wording ("archived stays" — redundant to say if the
rest were staying two fields) pointed at merging in the first place.

- **29 catalog entries migrated.** 27 from their keeping record's `state`,
  verbatim (`story-timeline`: `beta → gated`; `nasa-archive`: `stable →
  stalled`; etc. — full list in the commit). 2 with no record to read from get
  a manually-assessed status instead of a fabricated one: `utety-chat` →
  `gated` (it has a real CI-verified suite — `store-ci.yml`'s `app-tests`
  matrix — independent of its still-unresolved P1 relation question);
  `the-binder` → `stalled` (broken entry point + Cloudflare Pages shell, both
  confirmed in `docs/store_refit_survey.md`). `genealogy`, `llmphysics`,
  `llmphysics-bot` stay `archived`, unchanged.
- **`grove`/`willow-grove` also needed a value from the new closed enum** —
  the base status check applies store-wide, not just to P1/P3's in-scope
  entries, so their old `beta` would otherwise fail outright. Manually set to
  `building`: no evidence of brokenness, nothing to measure them against
  either, same open "loose repo" gap as before, just now expressed in the new
  vocabulary rather than the old one.
- **`tools/catalog_lint.py`**: `VALID_STATUSES` is now identical to
  `VALID_STATES`; the manifest-required check moved with it
  (`building`/`gated`/`stalled` require a manifest, `seeded` only warns, same
  softer treatment `coming_soon` used to get). `lint_generated_fields()`
  checks a stored entry's `status` against its record's `state` (was: a
  separate `state` field), and now also rejects a leftover `state` key on any
  catalog entry outright — the two-fields-for-one-fact shape this migration
  closed must not grow back.
- **`tui.py`**'s status→color/badge maps moved to the new words
  (`gated`→green/●, `building`→yellow/◑, `seeded`→dim/○, `stalled`→red/✕,
  `archived`→dim/✕, unchanged).
- **Tests**: `tests/test_p3_generated_catalog_fields.py` updated in place (14
  tests: status-vs-record consistency, the leftover-`state`-key guard, pending
  and promoted entries' status correctly *not* being checked against
  anything since neither has a record to check against). New
  `tests/test_status_vocabulary_migration.py` (6 tests) covers the base
  `lint()` checks the other file doesn't reach: the old vocabulary is actually
  rejected, all five new values are accepted, and the manifest-required tiers
  moved correctly. Verified both can fail: reverted `VALID_STATUSES` to the
  old set, watched exactly the two vocabulary tests redden, restored it; then
  set `story-timeline`'s real catalog status to `beta`, watched
  `catalog_lint.py --strict` catch both the invalid-status error and the
  now-mismatched-with-its-record error, restored it.
- **`README.md`** repointed: its app table's status column and its
  "gated means a CI-verified suite exists, not feature-complete" caveat now
  match the real values instead of the old shop words.

#### The spanning-relation gap — `the-binder` and `utety-chat` · done 2026-07-31

`stores/pending.json` named the open question, and `docs/store_refit_survey.md`
("Open gates") named the two ways out: grow the relation vocabulary a sixth
term, or give these two builds a rule of their own. **Decided explicitly: do
neither.** Both are now recorded with `relation: "unrelated-bundled"` — the
closest existing term, not an accurate one — and the mismatch is written into
each record's `notes` rather than papered over:

- `the-binder`: `python` + `browser`. The python side's `entry_point`
  (`willow.server:app`) resolves nowhere in this repo, and its own README puts
  the real backend on an external machine — confirmed by
  `docs/store_refit_survey.md` and issue #79. The `web/` Cloudflare Pages slice
  is the actual live product (calling Gemini/Groq, storing in browser
  IndexedDB). `unrelated-bundled` says "two separate products bundled under one
  `app_id`," which is close enough to describe a functioning frontend sitting
  next to a backend that doesn't run here, without inventing an anchor or
  claiming an equivalence ("alternate-deploy-targets") that was never verified.
  `state: stalled`, matching the broken entry point.
- `utety-chat`: `python` + `rust` + `browser`. The `python`/`rust` half is a
  verified `sidecar` (the `campus/` ratatui crate spawns `campus_consult.py` as
  a subprocess) — that fact isn't lost, it's stated plainly in the record's
  `notes` even though the record's single `relation` field can't carry two
  relations at once. The `browser` third axis (`web/`, a Cloudflare Pages
  deploy) is not a competing implementation of anything, just an alternate way
  to reach the same chat product — the shape neither `sidecar` nor
  `alternate-deploy-targets` names. `state: gated`: it's the one of the two with
  a real CI-verified suite (`store-ci.yml`'s `app-tests` matrix), independent of
  the relation question.

Both entries removed from `stores/pending.json` (now empty) and given real
records at `stores/python/stored/the-binder.json` and
`stores/python/stored/utety-chat.json` — filed under `python` on file count
(the-binder: 5 `.py` vs. 2 in `web/`+`functions/`; utety-chat: 23 `.py` vs. 5
`.rs` vs. ~13 in `web/`). Catalog entries for both gained a `majors` field to
match. Verified the gates that now cover these two aren't vacuous: dropped
`browser` from `utety-chat`'s catalog `majors`, confirmed
`catalog_lint.py --strict` reddens with the majors-mismatch error, restored it;
removed `the-binder`'s keeping record entirely, confirmed both the
coverage-gap error and the lint-invariant-violation error fire, restored it.

Left alone deliberately: `VALID_RELATIONS` still has five terms, not six. This
was the operator's call, made explicit rather than assumed — the two-builds
case didn't clear the bar for growing a vocabulary that every future spanning
build has to live inside.

### P4 — Discovery is not the house's job · independent

`discovery_sources` is the last purely-market organ: a curated directory of
third-party hosted tools to mine for ideas. Nothing in it is kept, provisioned,
or promoted, and its own `caveats` field says it isn't SAFE and must not carry
sensitive data. It is research input, and it belongs in `docs/`.

**Gate.** The catalog schema rejects unknown top-level keys, so the shelf cannot
grow a new organ without someone deciding to add one.

**Done 2026-07-31:** both `discovery_sources` entries (`public.tools`,
`public-apis-live`) moved verbatim — every field, including `highlighted_tools`,
`consumers`, `local_mirror`, and `willow_refs` — to
[`docs/discovery_sources.md`](discovery_sources.md); nothing dropped, only
reformatted from JSON to prose. `catalog.json` (`.willow/store/`) no longer has
the key. `tools/catalog_lint.py` gained `VALID_TOP_LEVEL_KEYS = {"version",
"store", "description", "apps"}` and a check that rejects anything else —
`tests/test_catalog_top_level_keys.py` proves both a `discovery_sources` regrowth
and an arbitrary new key are actually caught, not just the currently-clean state.
Nothing else in the repo read `discovery_sources` (checked before moving it), so
this was a pure extraction: no consumer to update.

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

## Settled in review

**Which major owns a build that spans two crafts** — raised as the gate blocking
P1, answered on the measurement rather than on preference. Both new builds are
near-even, counted on the tree that tracks the browser halves:

| | `.py` | `.ts` | `.mjs` |
| --- | ---: | ---: | ---: |
| `marching-arts` | 15 | 14 | 6 |
| `field-acoustics` | 15 | 13 | 8 |

A primary-major rule would decide those on a coin flip. But the ratio is the
weaker half of the argument: in neither build are the two languages *two
components*. They are **two implementations of one component, held together by a
differential suite** — `field-acoustics/kernel` against `dcisim`, and
`marching-arts/browser` against the resolver across 27,528 comparisons. So a
primary-major record would state something false about where the code lives, and
the P1 gate would then be **enforcing that falsehood rather than catching
drift** — which is the whole reason the gate exists.

Resolved as record-both, plus the relation, filed under the anchor major. The
first draft of P1's gate asserted *"no build appears under two majors"* and would
have made this unrepresentable; it is corrected above.

## Open gates — all three resolved

- **`llmphysics` has no manifest.** — **Already resolved, doc was just stale.**
  This bullet described a decision that had, in fact, already been made: P1
  gave `llmphysics` a real keeping record (`stores/browser/stored/llmphysics.json`,
  `state: archived`) noting the manifest is in the wrong dialect
  (`safe-app-manifest.js`, not missing), and the status-vocabulary migration
  left its catalog `status: archived` unchanged. Caught during the
  documentation-accuracy pass (2026-07-31): this section itself had drifted
  from the tree — the exact class of problem the rest of that pass fixed
  elsewhere.
- **Loose repos.** — **Resolved 2026-07-31: pending, not archived.** `grove`
  and `willow-grove` are named in `stores/pending.json` with a reason
  (unreachable from this account) and a `blocked_on` (repo becomes reachable,
  or the operator later decides unreachable should mean archived instead).
  New gate: `tools/catalog_lint.py`'s `lint_loose_repos()` requires every
  pathless, non-archived, `repository`-bearing catalog entry to be named in
  `stores/pending.json` or have a real keeping record — a claim about code the
  house cannot reach is worse than an explicit, reasoned absence.
  `tests/test_loose_repos.py` proves it; verified against the real repo by
  removing `grove`'s pending entry and watching the gate redden, then
  restoring it.
- **Who witnesses?** — **Resolved 2026-07-31, documented rather than
  mechanized.** `promote_check.py`'s `verified_by ≠ author` check is exactly
  what it looks like: a string-inequality convention, satisfiable by typing
  any second name into the field — not proof of independent review. The
  operator's explicit call: leave it as-is rather than gate it against an
  allowlist of recognized reviewers, because the alternative (blocking every
  promotion until a second real reviewer is configured) stops a
  single-operator fleet from ever promoting anything. Stated plainly here so
  the gap is a known, accepted trade-off rather than something discovered the
  first time a promotion is refused: for a single operator, this check forces
  a deliberate second pass, and that is what it verifies — not that a
  different person made it.

---

*The head of this house is the architect, not a shopkeeper.* `ΔΣ=42`
