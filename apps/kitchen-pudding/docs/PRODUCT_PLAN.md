# Product plan

## What this is

**Revised.** Not a solo recipe box — a way to bring people together over
food, using recipe verification as the reason two strangers start talking.
P0 (merged, #142) built the provenance mechanism as data hygiene: every
ingredient carries `measured`/`fitted`/`assumed`, and a recipe is worth its
weakest ingredient via `min()`. Turns out that mechanism is more interesting
pointed at other *people* than pointed at a solo user's own recipe box —
"I can verify this needs more flour at my altitude" is a reason to connect,
not just a data quality flag. See "The pivot" below for what that means
concretely. The P0 framing (below, kept for the record) is superseded, not
deleted — same "corrections land beside the record" discipline applied to a
plan doc instead of a recipe.

### Landscape check (2026-08-01)

Surveyed before committing to this direction — full notes in conversation,
summarized here for the record:

- **Buy Nothing's own app** shares the *opposite* of what this wants: it
  auto-saves your exact address and drops it into a private message per
  exchange. A stricter disclosure model than the app you're already in is a
  real differentiator, not a nice-to-have.
- **OLIO** is the closest existing shape (photo → neighbor requests → agree
  pickup) but has no verification layer at all — no provenance, no "this
  needs adjusting," just listings.
- **Every high-altitude baking resource that exists is a static published
  formula** (King Arthur, Exploratorium, calculator sites) — "+1-2 tbsp per
  3,000 ft," not per-recipe, not crowdsourced, not attributed to a person who
  actually tried it at your elevation. Nobody has built the thing this app
  does. Strongest signal that the idea, not just the execution, was missing.
- **DP3T** (COVID contact tracing) is the proven mechanism for "confirm
  proximity without resolving identity until it matters" — rotating,
  meaningless IDs exchanged locally, identity resolved only on a real match.
- **Earthstar** is a p2p, offline-first, scoped-group document sync engine —
  a serious candidate for *not* building a central server, see "Open
  questions" below.
- **Community Notes' bridging rank** — a correction/note only surfaces once
  people who normally *disagree* both find it helpful — is sharper than a
  plain append-only log for a multi-author correction stream. Worth adapting,
  not adopting whole (see below).
- **Timebanking/LETS software (Cyclos, WebLETS, openLETS)** — sound idea
  (track reciprocity without money), dead 2000s-era code. Not a foundation.
- **Mutual Aid Wiki / MutualAidNYC** — the *dispatcher-mediated* trust model:
  a volunteer bridges a need and an offer so neither party sees the other's
  address directly. The middle rung of the ladder below is this pattern,
  minus the human dispatcher.

## What P0 was (superseded framing, kept for the record)

A recipe box, not a meal-planning suite. The one thing that was different
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

## Noted: a candidate display format

A recipe card spotted 2026-08-01 (grid layout: ingredients as rows on the
left, columns to the right showing `melt` / `mix` / `mix` / `fold in` /
`bake`, each ingredient's row terminating at the column where it enters)
does something most recipe formats don't — ingredients and instructions in
one box, with column position telling you *when* something enters instead of
a separate numbered sentence for it.

Worth keeping for whenever the interaction layer moves past the CLI (see
"Settled" above — deliberately not designed yet). Two things worth noting
now, before that phase, so they're not rediscovered the hard way:

- **It requires `Recipe.steps` to stop being a flat list of strings.** The
  card encodes a small DAG — which ingredients converge at which stage —
  and today's model has no structure to hang a merge point on. If steps ever
  need to render this way, that's a model change, not a display change.
- **Each merge point is itself a provenance claim.** "Fold the dry
  ingredients in last" can be `measured` (the card author actually tested
  order) or `assumed` (nobody's confirmed order matters) — same discipline
  as ingredient quantities, just applied to structure instead of amounts.

## The pivot: a three-rung disclosure ladder

Not "how much do I hide" but "how do two people earn their way to an
exchange." Same shape whether the interaction is verifying a recipe or
offering to bring someone flour — that's the point of the pivot, one
mechanism serves both halves of "bringing people together over food."

1. **Anonymous match.** "Someone in your group verified this needs more
   flour at altitude" / "someone nearby has flour to spare." No name, no
   location finer than the group. Where most interactions stay — this is
   where the P0 provenance/correction mechanism already lives, just made
   multi-author.
2. **Named, still vague.** Both sides opt in and it becomes "Jamie, three
   blocks over, verified this" / "Jamie has flour." First name and rough
   proximity, not an address. About what a Buy Nothing post looks like
   before you've claimed anything.
3. **Handoff, mutual and explicit.** Only when *both* people confirm does
   anything precise change hands, peer-to-peer, never stored by the app.
   Same shape as the sealed-grant consent model already built in
   `marching-arts`: a grant only exists because a named person sealed it,
   and revoking deletes rather than flags. Applied here to "can you see my
   street" instead of "can you see my roster record."

The app's responsibility ends at rung 3's threshold: it marks a match as
"handoff pending" and gets out of the way. No address field anywhere in the
schema, no messaging feature to build. Keeps "no export path rather than a
disabled one" (CLAUDE.md) literally true — there is no code path in this app
that ever transmits an address.

## P1: what the ladder needs, concretely

Gaps this surfaces that P0's single-user design didn't have to face:

- **A Group model.** P0's `store_scope` (`kitchen_pudding_*`) is a
  single-vault namespace. P1 needs it to generalize to a shared namespace
  per group (`kitchen_pudding_<group_id>_*`), the same store-scope wall the
  rest of this repo already enforces for apps, now enforced between groups
  within one app.
- **Membership.** Invite-only, matching Buy Nothing's private-group model —
  open discovery is explicitly not the goal. Who can invite, and who
  removes a bad actor, is a real question (see "Open questions").
- **Corrections need a submitter.** P0's `store.py` correction schema has no
  `who` field at all — it was written for a single user correcting their own
  recipes. That's a genuine gap this pivot exposes, not glossed over: rung 1
  needs *some* identity (even pseudonymous) attached to a correction, or
  there's nothing for rung 2 to name later.
- **Bridging-lite surfacing.** Not the full Community Notes algorithm, but
  the same idea: a correction from someone in a different self-reported
  elevation band agreeing with an existing one should outrank a second
  correction from someone in the same band. Otherwise ten neighbors at the
  same altitude look like stronger evidence than they are.
- **Sync architecture — the single biggest open fork.** A single-device JSON
  store doesn't work once there's more than one person. Real options, not
  yet decided: (a) a small self-hosted sync server per group, most control,
  breaks the "no server" ethos; (b) Earthstar-style p2p sync scoped per
  group, keeps local-first, unproven in this codebase; (c) a Postgres
  instance per group, no different in shape from `private-ledger`'s existing
  shim. This has to be decided before P1 schema work starts, not discovered
  partway through it.

## The "bring you some" matching (next-next bite, not P1)

- Offer/need posts scoped to a group, rung 1 only — no identity needed to
  see "someone needs flour."
- Matching is declared-need vs. declared-offer *within a group*, no
  geocoding, no lat/long. The group boundary already is the proximity
  boundary, same as a Buy Nothing group. This sidesteps most of the
  privacy-preserving-proximity literature (DP3T etc.) because the group is
  invite-scoped from the start, not global.
- Explicitly out of scope even here: reputation/rating systems, payment,
  delivery logistics.

## Open questions before writing any P1 code

1. **Sync architecture** — self-hosted server vs. Earthstar vs. a
   Postgres-per-group shim. Three real options; needs a decision, not a
   default.
2. **What "anonymous" means at rung 1.** Literally anonymous (no persistent
   identity, even within a group) defeats bridging-lite surfacing, which
   needs *some* stable-but-unlinked identity to tell "two different people
   agree" from "the same person posted twice." Pseudonymous-stable within a
   group, resolved only at rung 2, is the likely answer — not yet decided.
3. **Group moderation.** Buy Nothing groups have moderators. A P1 with no
   admin role and no way to remove a bad actor is a known gap if shipped
   that way, not an oversight — needs an explicit decision either way.

## Next bite

Answer the three open questions above — a scoped design conversation, not
code. Once decided, P1 starts with: the Group model, a submitter field on
corrections, and the sync architecture choice, in that order.
