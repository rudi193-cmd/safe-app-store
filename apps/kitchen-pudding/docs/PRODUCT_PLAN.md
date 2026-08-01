# Product plan

## What this is

A recipe box, not a meal-planning suite — yet. The one thing that's different
from Mealie/Tandoor/KitchenOwl (all surveyed, all AGPLv3, none forked): every
ingredient carries a provenance tag, and a recipe's overall trustworthiness is
the weakest ingredient in it, not an average. "2 cups flour" from a tested
recipe card and "2 cups flour" guessed off a food photo are different claims,
and none of the existing open-source options say which one you're looking at.

## Settled

| Decision | Choice |
| --- | --- |
| License | Apache-2.0 — not AGPL, deliberately; see `safe-app-manifest.json` notes |
| Storage | Local JSON under the vault (`libs/vault-paths`), one file per recipe |
| Aggregation | `min()` over ingredient provenance, never a mean (CLAUDE.md discipline) |
| Corrections | Append-only log beside the original; the original file is never rewritten |
| Interaction layer | CLI first. A UI is a later phase, not a blocker. |

## P0 — done in this scaffold

- `Provenance` enum (measured/fitted/assumed) with `min()`-based aggregation
- `Recipe`/`Ingredient` models
- `RecipeStore`: immutable original + append-only correction log, replayed by
  `current()`
- CLI: `add`, `list`, `show`, `correct`
- Tests for both mechanisms — the aggregation and the append-only-ness are
  each covered by a test that specifically fails if the *mechanism* breaks,
  not just if the CLI's output string changes

## Open — not built, not decided

- **Mechanism vs. preference isn't schema-enforced yet.** The pudding-app
  bit from planning: provenance is a mechanism claim (checkable), taste/rating
  is a preference claim (votable), and the two should never be able to
  overwrite each other. Right now nothing stops a future `rate()` call from
  writing into the same correction log as `correct()` — there's no type-level
  wall. Needs a decision on whether preference gets its own log entirely
  before any rating feature lands.
- **Absence as a recorded value.** CLAUDE.md: "a row that says 'no
  competition happened' and no row at all are different facts." Right now a
  missing ingredient field is just missing — there's no way to record "this
  recipe deliberately has no sugar" versus "nobody's entered the sugar yet."
  Worth doing before this app has enough recipes for the difference to matter.
- **Meal planning, shopping lists, pantry tracking.** All out of scope for
  P0. If they get built, they're a second data stream on top of this one, not
  a rewrite of it — recipes stay the unit of record.
- **Import from existing recipe sites.** Mealie's URL-scrape feature is the
  single most useful thing about it. Not attempted here yet; would need its
  own provenance story (a scraped ingredient list is `assumed` until someone
  cooks it and confirms the quantities, which is itself a workflow this app
  doesn't have yet).
- **Promotion.** This is a P0 playground build (`stores/python/stored/kitchen-pudding.json`,
  `state: building`) — not in the CI matrix, not gated, not promoted. See
  `safe-app-store/CLAUDE.md` §8 for what promotion requires.
