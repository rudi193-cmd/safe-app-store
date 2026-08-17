# Homestead Kitchen — a vision note (companion to the Table)

> **Status: reflection, not a spec. Nothing is built from this.** Proposed for
> ratification where it decides (`verified_by ≠ author` — drafted at the
> operator's direction, awaiting a person's seal). Drafted 2026-08-17, grounded
> by three scouts (organs, recombination-feasibility, external OSS) whose notes
> live under the session scratchpad. Companion to
> [`homestead-table-vision.md`](homestead-table-vision.md); read that first.

## Where this came from

Two moves led here. First, gaming was split out of `the-table` into its own
pinning module (records that must stand later). What was left of the table — the
meals, the gathering, the kept-clear surface — is exactly what the table vision
note called **the Table**: module three, the surface *defined by what it refuses
to hold*. Second, the operator named a **kitchen**: recipes, and "the other stuff
the table holds for a family."

Those are the same room. **The kitchen table collapses the vision note's abstract
Table and the concrete kitchen into one object.** It was never "Table" versus
"kitchen" — the kitchen table is the thing a household actually gathers around, and
naming it that resolves the tension the table note left in its own title.

## A loop that closes: the Sidecar was born here

`kitchen-pudding` is a local-first recipe store whose one distinctive mechanism is
a **correction-log**: `add()` refuses to overwrite, `correct()` appends beside the
record, `current()` replays corrections over the original — the original claim
always still answerable. The table vision note states outright that this is where
the engine's own correction model came from: *"corrections go in a Sidecar beside
the record, never on top — kitchen-pudding's correction-log pattern, formalized."*
`homestead/keep/store.py`'s `Canonical`/`Sidecar` **is** that formalization.

So the engine's DNA was born at the kitchen table. If `homestead-kitchen` ever
promotes onto `homestead.keep`, the pattern comes home.

## What a kitchen table does — and what the house already has for it

| Table function | Built organ(s) | Reuse |
|---|---|---|
| recipes / "what's for dinner" | **kitchen-pudding** (recipes, `measured/fitted/assumed` provenance) | adapt |
| games / crafts / play | **the-table** (`GameSession`, registry, `story_session` propose→seal, "players never recorded"); **band-camp-arcade** (no per-kid trace) | drop-in |
| family stories | **the-squirrel** (resolved `persons` vs raw `fragments` + confidence) | reference / adapt |
| the mail pile it *refuses* to hold | **Law + Ledger** (so the surface stays clear); **nest-seed** / `libs/nest-pipeline` (ingestion) | adapt |
| worries / check-ins | **homestead-health**'s living lane | shared (see below) |
| scaffolding | law/ledger's ~40-line `store.py` subclass + pack pattern; `libs/vault-paths`, `libs/subject-consent` | drop-in |

The games leg is the best-covered — records-optional play already exists. The
recipe leg has a real base. The rest is genuine, if bounded, new work.

## The recombinations, honestly

An earlier pass pitched three "clever" recombinations as near-free reuse. The
feasibility scout cooled all three against the actual code, and the honest version
is worth keeping so the next seat doesn't re-pitch the rosy one:

1. **The allergy gate was pitched backwards.** "Reuse H-7 unchanged" was wrong:
   H-7 says a reference-fact and a subject-record *never share a surface*, which is
   the *opposite* of what a flag needs — it must **join** "this dish contains
   peanuts" (a thing) against "someone here is allergic" (a subject). Plus
   CLAUDE.md §6 bars kitchen-pudding and homestead-health from reading each other,
   so any gate lives **inside** `homestead-kitchen`, pinning both as libraries. It
   is new work, and it surfaces the open decision below.
2. **Provenance is one *concept*, not one *primitive*.** Only kitchen-pudding's is
   a real ordered type (`IntEnum` + `min()`, "weakest wins"). the-squirrel's
   `confidence` is a flat string with no ordering or aggregation; health's H-4
   composes via `max()` — the opposite direction. A shared seed can be lifted from
   `kitchen_pudding/provenance.py` into `libs/`, but the-squirrel then needs new
   logic for *conflicting* fragments that a non-conflicting ingredient list never
   faced.
3. **The list is a second data stream, not a derivation.** kitchen-pudding has no
   pantry, on-hand quantity, or unit type; its own product plan already says
   grocery/pantry/meal-plan is "a second data stream on top of this one, not a
   rewrite." The forgetting-cell reuse is directionally right but shaped for L5
   no-egress data, and a grocery list needs to be *read*.

## The one primitive worth building once

Every organ in the box is built to **never lose data**. There is no
"replace-in-place / forget-on-purpose" store anywhere. That is `homestead-health`'s
living-lane **forgetting cell** — and the kitchen needs it three ways (the weekly
list, the worries surface, "what's on the table right now"). It is not a
health quirk; it is **the household's single missing primitive.** Build it once;
health and kitchen both consume it.

## External parts (Apache-compatible)

- **SET ASIDE (copyleft):** Mealie, Tandoor (+ an incoherent Commons Clause),
  KitchenOwl — all AGPL. Comparison only.
- **Grocy** (MIT) — a full stock/list/meal-plan/recipe feature set that is actually
  permissive; a real data-model read is worth it.
- **CookLang** (`cooklang-rs`, CookCLI — MIT) — recipes as plain-text `.cook`
  files, git-diffable, offline. This is homestead's own file-owned ethos; a strong
  candidate storage/interchange shape.
- **USDA FoodData Central** (CC0, 300k foods) — the public-domain "what's in this
  food" corpus; the reference backing for the allergy gate, the way MedQuAD backs
  health's reference lane.
- schema.org/Recipe (CC0) + `recipe-scrapers` (MIT) for optional URL import;
  rrule.js / Xandikos / khal (MIT/BSD) for a calendar side. Open Food Facts is
  ODbL — cached read-only with attribution, caution on redistribution.
- **Recipe-copyright, plainly:** bare ingredient lists and functional steps are not
  copyrightable; headnote prose, photos, and creative selection/arrangement are. A
  "walk the recipe-card folder" ingestion may keep ingredients+steps and must treat
  prose/photos as the family's own authorship, not third-party verbatim.

## The open decision — the safety flag vs. the privacy cover

This is the deepest thing the kitchen surfaces, and it is genuinely unresolved.

Homestead's re-identification cover (`DECISION-cover-re-identification.md`, the
k ≥ 2 math) **suppresses** a count or flag when rendering it would name an
individual — "1 immunization due" over a one-child household names the child, so it
renders nothing. That protects the subject.

An allergy flag needs the opposite. *"This dish is unsafe for someone at this
table"* must fire even when **exactly one** person is allergic — because that one
person is the whole point. Run the safety flag through the k ≥ 2 cover and it goes
**silent at k = 1**, the case that matters most. The same math that protects the
immunization count becomes a dangerous silence for the safety flag. **Privacy-
suppression and safety-alerting point in opposite directions.** No other homestead
module has faced this; health only ever needed to suppress.

**A proposed resolution direction (proposed, not sealed — the carve-out is a value
judgment, and by §0.2 a model may only propose it):**

- **Split the axes.** The flag is a fact about the **dish** ("do not serve this
  here"), which may fire at k = 1. The **who / how-many** is subject-data, and
  *that* stays under the k ≥ 2 cover and the detail-gate. The cover math governs
  the count and the identity — never the safety boolean.
- **Frame it as a constraint, not a disclosure.** The kitchen says "don't serve
  this dish," never "Mara is allergic." It mirrors a constraint on an *action* and
  authors no claim about a *person* — mirror-not-judge, in a new form.
- **It is the emergency card's cousin (H-3).** A datum whose purpose is to protect
  in the worst minute; the health plan already ruled that usefulness does not
  declassify — the answer is an *authored, gated* surfacing, not a lowered rung.
  The operator authors "flag dishes against the household's allergy set"; the flag
  fires as a constraint; the subject never renders.

**The residual that no math closes:** in a very small household, even a dish-only
flag can let an observer *infer* that someone is allergic. That inference cannot be
computed away. Whether the duty of care outranks that marginal re-identification
risk is a **ruling**, not a calculation — precisely the kind of decision the house
holds only a person may seal, with the reason recorded (the Nestor / decision-record
posture). This note proposes the carve-out; it does not make it.

## What this note did not do

- **Built nothing.** This file is the only write.
- **Did not create `homestead-kitchen`**, a pack, a registry stub, or the
  forgetting cell. Named the shape, rated the reuse honestly, and left the safety-
  flag carve-out as an open decision for a human seal.
- **Did not decide the naming.** `homestead-kitchen` is the working name; the
  module is the Table made concrete, whatever it ends up called.

## Related

- [`homestead-table-vision.md`](homestead-table-vision.md) — the companion; the Table as the kept-clear surface
- `apps/kitchen-pudding/` — the recipe base and the correction-log the Sidecar was formalized from
- `homestead/docs/PLAN-homestead-health.md` — the three-postures extension; the forgetting cell and the H-7 wall
- `homestead/docs/DECISION-cover-re-identification.md` — the k ≥ 2 cover the safety flag collides with
