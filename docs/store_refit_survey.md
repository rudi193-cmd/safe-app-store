# The playground survey — what the storehouse is actually holding

b17: SAPS1

Input for **P1** of [`store_refit_plan.md`](store_refit_plan.md), which said the
keeping record should state a build's majors, anchor, relation, lane, state and
gaps. Before a record can state those, someone has to measure them. This is that
measurement, across all **27** playground builds.

Six agents, disjoint build sets, read-only. Every figure below was measured from
the tree, not read off a README — which matters, because the single most common
finding is a document disagreeing with its own code.

> The failure is never in the step you are watching.

**The plan survives. Its gate does not, as written.** P1 assumed four things
about its own inputs, and the survey broke all four. That is the useful outcome:
the assumptions were invisible until something tried to read them.

---

## What P1 assumed, and what is true

| P1 assumed | Measured |
| --- | --- |
| Manifests share a shape, so `store_scope` is readable | **At least four dialects.** The standard `.json`; `bt-controller` using `safe_consent` and omitting `entry_point`/`license`/`repository`; `llmphysics` shipping `safe-app-manifest.**js**` (`scopes`/`dataPolicy`/`entry`); `story-timeline` declaring reach as **`sap_scope`**, not `store_scope` |
| A build with no `store_scope` has no declared lane | **False for `story-timeline`** — `sap_scope: "user-{uuid}/story-timeline/**"` is a real declaration under a legacy key. A gate grepping for `store_scope` doesn't just miss it, it *discards* it |
| `repository` gives the location | **Not ground truth.** Of four claims checked: `oakenscrolls-office`'s exists (and its README calls the in-tree copy *non-canonical*, "keep in sync", with no mechanism); `ratatosk`'s is self-referential and correct; both ledgers' 404 unauthenticated — undetermined, not disproven |
| No-anchor is the exception (2 named builds) | **It is the rule. 2 of 27 have a principled anchor.** Both are differential pairs; every other spanning build has none |

---

## The anchor rule covers two builds

Anchor was defined as *the implementation that defines what correct means*. Where
a differential suite exists, it isn't a judgment call at all — the repo says it
outright:

- `field-acoustics` — `kernel/README.md`: *"the reference **is** the Python."*
  `gen_reference.py` runs `dcisim`; `differential.mjs` replays it through the port.
- `marching-arts` (on PR #114, not yet on master) — `browser/test/gen_reference.py`:
  *"If the two disagree, Python is right by construction."* 27,528 comparisons.

Everywhere else the crafts span **without** a reference implementation, and the
relation is a different shape each time. One term is not enough:

| Relation | Build | Held together by |
| --- | --- | --- |
| `differential-paired` | field-acoustics · marching-arts (#114) | a differential suite |
| **sidecar** | `utety-chat` — Rust `campus/` spawns `campus_consult.py` as a subprocess | a runtime call |
| **runtime-fallback** | `vision-board` — FastAPI/Ollama backend vs. in-browser TF.js classifier | **nothing** |
| **alternate deploy targets** | `llmphysics-bot` — PRAW-Python vs. Devvit-Node, *"pick one — they do the same thing"* | **nothing** |
| **unrelated, bundled** | `the-binder` · `nasa-archive` · `ask-jeles` | nothing — separate products under one `app_id` |

`vision-board` is the one to stop on. Two independently written classifiers with
**different `CATEGORY_MAP` vocabularies**, no shared source, no test asserting
they agree — and `App.jsx` selects between them at runtime by whichever is
reachable. The same photo classifies differently depending on network state.
That is #83's drift hazard at the semantic level rather than the file level, and
naming the relation is exactly what would have surfaced it.

**`utety-chat` also spans `python` + `rust`** (a full ratatui crate), which
nothing in the plan anticipated.

### And some builds fit no major at all

`the-binder`, `llmphysics`, and `utety-chat`'s web slice are Cloudflare Pages
sites — static HTML with inline `<script>`, a Pages Function, no `package.json`,
no build tooling. `stores/README.md` defines `node` as *"Node.js · Ink · Electron
· CLI"*. Filing a Pages site there would be the same class of falsehood as
primary-major. **The majors list has a gap, not these builds.**

---

## Eight declared entry points do not resolve

Verified independently of the agents, checking flat and `src/` layouts:

| Build | `entry_point` | |
| --- | --- | --- |
| `dating-wellbeing` | `dating_wellbeing.main:app` | no such package anywhere |
| `game` | `safe_integration:status` | module exists, no `status()` |
| `nasa-archive` | `pipeline.main:app` | no such module |
| `public-ledger` | `safe_integration:status` | resolves only into `_archived/` — dead code its own README says nothing imported |
| `the-binder` | `willow.server:app` | **resolves nowhere in this repository**; README puts the backend at `C:\Users\...` |
| `the-nightstand` | `app:main` | module exists, no `main()` |
| `utety-chat` | `utety_chat.app:run` | no such package |
| `llmphysics` | — | no `.json` manifest at all |

`nest-seed` is a ninth of a different kind: its entry point exists but imports
`nest_pipeline` and `vault_paths` from `libs/`, neither installed nor on
`sys.path` by any path the Makefile takes — it fails at import, not structurally.

`llmphysics` needs a correction to what the plan says: it does not *lack* a
manifest, it has one in the wrong dialect. "Missing manifest" was too coarse.

---

## Rulings the survey needs, which are not the refit's to make

- **A non-commercial licence in an Apache-2.0 house.** `utety-chat` declares
  three licences across three files in one tree: `LICENSE` is **CC BY-NC 4.0**,
  the manifest says MIT, `pyproject.toml` says Apache-2.0. `stores/README.md`
  says the house is *"Open. Apache-2.0."* This is a conflict, not a typo.
  Thinner versions: `dating-wellbeing` (MIT vs Apache-2.0, `LICENSE` truncated to
  two lines); `vision-board`, `ratatosk`, `nest-seed`, `semantic-translator` all
  claim MIT with **no `LICENSE` file**; `story-timeline` has neither.
- **`nasa-archive` is not what its manifest says it is.** The manifest describes
  *"NASA open datasets — imagery, mission telemetry, earth science."* The product
  is a scooter-rally memory archive — *North America Scootering Archive*, a
  backronym — and `SPEC.md` self-diagnoses it as three projects mashed together.
  This is a deeper drift than issue #78, which only names the entry point.
- **`llmphysics`: the catalog got ahead of the plan.** The plan lists held-or-
  archived as the operator's open decision; `catalog.json` already records
  `"status": "archived"`.
- **`llmphysics-bot` contains a build that isn't it.** `gerald-bot` — different
  persona, different subreddit, self-described *"scaffold only… untested"* — sits
  inside an `app_id` the catalog marks `archived`/handed off. One record cannot
  honestly describe both.
- **`oakenscrolls-office` is the loose-repo case, live.** Its README declares the
  in-tree copy non-canonical against an external repo that does exist, with a
  stated sync obligation and nothing enforcing it.

---

## Catalog drift: every open issue checks out

Verified independently rather than inherited from the issue text.

| Issue | Claim | Measured |
| --- | --- | --- |
| #78 | `nasa-archive` `stable`, entry point broken | confirmed — **and** the product identity is wrong too |
| #79 | `the-binder` "local-first", is a Pages shell | confirmed — Pages site calling Gemini and Groq, storage is browser `IndexedDB`, nothing writes the `willow_knowledge.db` the manifest claims |
| #80 | `game` broken entry point | confirmed — **but** `CODE_REVIEW.md` is stale the other way: 3 of its 4 "will crash" findings are already fixed |
| #81 | `utety-chat` "11 faculty" | confirmed — `personas.json` has 19, the manifest's own `professors` array has 20. "11" matches neither |
| #82 | `vision-board` "96% client-side" | confirmed — the 4% traces to a design budget in `PRODUCT_SPEC.md` (OAuth broker, telemetry, update endpoint) **none of which exist in code**, against a manifest declaring `local_processing: 1.0` |

Two not yet filed: `civics-check`'s catalog entry claims *"no dependencies"* while
requiring `textual` (true only of an undocumented `--cli` fallback), and
`law-gazelle` sits at `coming_soon` with 41 modules, 9 test files, an MCP surface
and a demo path.

---

## What this changes in the plan

1. **P1's gate must normalise before it judges.** Manifest dialect and key name
   are resolved first; only then can a lane be called absent. As written it would
   have reported `story-timeline` unscoped and skipped `llmphysics` silently —
   a gate that fails open on the builds least like the others.
2. **`relation` is a closed enum of five, not one term**, and `anchor` is
   **optional** — required only for `differential-paired`. Anything else records
   the relation and leaves anchor empty rather than inventing one.
3. **`majors` needs a seventh value or an explicit `unclassified`** for Cloudflare
   Pages builds. Forcing them into `node` reintroduces exactly the falsehood
   record-both was adopted to avoid.
4. **`location` is measured, never transcribed** from `repository`.
5. **P0 grows one line**: the same normalisation applies to the *tier* vocabulary,
   since `_archived/` means at least three different things across the tree —
   retired app code (`private-ledger`), an extracted dependency
   (`semantic-translator`), and superseded files kept per §4 (`law-gazelle`). A
   gate reading directory names would mark all three archived.

None of this changes the shape of the refit. It changes what P1 has to survive
contact with, and every item above is a fact the keeping record is *for*.

---

*Absence is a value, not a gap.* `ΔΣ=42`
