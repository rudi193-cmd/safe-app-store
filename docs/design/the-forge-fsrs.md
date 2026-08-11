# The Forge — folding real FSRS into bite 2's scheduler (design, 2026-08-11)

> Bite 2 (`stores/checkpoint_calibration.py`) shipped with `is_due` as a
> **fixed-interval, stdlib-only placeholder**, explicitly deferring the real
> scheduler until the Apache-compat reuse-map named one. It has:
> **`py-fsrs`** (PyPI `fsrs` **6.3.2**, **MIT**, only transitive dep
> `typing-extensions` — dependency-light, clears the promotion bar; and the
> same library D9 named at the very start, before the `engram` phantom
> detour). This doc settles the parts of the fold-in that are **design
> decisions, not wiring**, so the build after it is mechanical. Nothing here
> is built yet.

## Why this isn't a "swap the body of `is_due`" one-liner

Grounded in the real 6.3.2 API (inspected, not remembered):

- `fsrs` exports `Card, Rating, Scheduler, ReviewLog, State`.
- `Rating`: `Again=1, Hard=2, Good=3, Easy=4`.
- A `Card` carries `card_id, state, step, stability, difficulty, due,
  last_review`. A fresh card has `stability=None, difficulty=None, due=now`.
- `scheduler.review_card(card, rating, review_datetime=None) -> (Card,
  ReviewLog)` returns the **updated** card, whose `due` is the next
  review time — computed from that card's own memory state and the rating,
  **not** from a fixed interval.
- `Card.to_dict()` is JSON-safe and `Card.from_dict()` round-trips it
  exactly (verified: `due` and `stability` equal after a round trip).

So FSRS is *stateful per seal*. The fixed-interval placeholder answered "is it
due" from `(last_reviewed, interval_days)` — two scalars. FSRS answers it from
a **persisted card** that changes on every review. That forces three decisions
the placeholder never had to make.

---

## D-FSRS-1 — Where the per-seal card state lives: **a Forge-owned sidecar, not the Nestor seal**

**Decision: a sidecar store the calibration layer owns**, keyed by the
resurfaced decision's **Nestor `pair_id`** — the *question*, not the answer —
holding one `Card.to_dict()` blob per resurfaceable decision. It sits under the
same checkpoint root the memory layer already uses
(`checkpoint_memory.DEFAULT_CHECKPOINT_ROOT`), in its **own per-builder file**
(`<builder_id>.schedule.json`), never inside Nestor's store.

> **Build-time refinement (2026-08-11):** the design first said key by
> `(builder_id, decision_type, surface_norm)`. Verified empirically that
> `resolve()` returns a stable `pair_id` in its provenance, and — because a
> regression reseals *in place* (bite 2's own finding: same verifier → same
> `pair_id`, only `target_text` changes) — **that `pair_id` is stable across a
> held→regressed→held cycle** (measured: id unchanged, canonical flipped
> `session cookie + CSRF` → `JWT bearer`). Keying on it is the faithful
> realization of "key by the question": one card follows the decision through
> every review, so regression grading the *same* card `Again` (D-FSRS-2) falls
> out for free, and the surface-normalization / reword-matching question never
> has to be answered. `surface_norm` would have fragmented the card the moment
> a maker reworded — `pair_id` doesn't.

**Why not inside the Nestor seal (the rejected door):**
- A Nestor seal is a **signed, human-witnessed commitment** — its schema is
  "what was decided, by whom," cryptographically. FSRS card state is
  **mutable scheduling bookkeeping** that changes on *every* review. Writing
  mutable state into a signed envelope either invalidates the signature on
  each review, or forces the state outside the signed part anyway — so it
  never actually belonged in the seal.
- **D6 / rule 6:** the Forge's calibration layer owns its own lane. The
  schedule *is* the Forge's concern, not Nestor's — Nestor is deliberately a
  soft dependency (bite 1), and a Forge-owned sidecar keeps it that way: you
  can read/write the schedule with Nestor absent (see D-FSRS-4).
- Keying on `surface_norm` (the same normalization Nestor uses to match a
  resurfaced wording) means the card and the seal find each other without the
  card living inside the seal.

**Closed sub-question — regression does NOT delete the card.** When a resurface
regresses and reseals a new answer, keep the *same* card and grade it `Again`
(D-FSRS-2). FSRS already models a lapse as a stability reset; that is the
native, correct behavior, and it keeps the review history continuous rather
than pretending a changed-mind decision is a brand-new one.

---

## D-FSRS-2 — The grade map: **held → Good, regressed → Again; Hard/Easy reserved for bite 3**

`resurface()` produces exactly two outcomes today: **held** (the maker still
holds the seal) and **regressed** (they don't). Map them to the two FSRS
ratings that mean the same thing:

| resurface outcome | FSRS rating | why |
|-------------------|-------------|-----|
| **held** | `Good` (3) | it held; graduate the interval normally |
| **regressed** | `Again` (1) | the memory failed; FSRS resets stability — a lapse, exactly what a changed mind is |

**`Hard` (2) and `Easy` (4) are deliberately not used in this bite.** They
encode *how* confidently a memory was recalled — a shaky-but-held vs an
instant-confident hold. The Forge does not capture that signal yet. **Bite 3
(the engagement gate, `#66`/`#67` friction-floor / mirror detector) is exactly
that signal**: a rubber-stamped "yes, still holds" is a weaker hold than a
maker who re-argued it. So the grade function is built now with a **named seam**
for bite 3:

```
grade(outcome, engagement=None) -> Rating
    # bite 2:  held->Good, regressed->Again  (engagement ignored)
    # bite 3:  held + low engagement  -> Hard   (barely holds; resurface sooner)
    #          held + high engagement -> Easy   (re-argued and held; push it out)
```

This keeps the mapping **non-circular** — we grade *whether the maker still
holds their own decision* (a behavioral fact they report), never whether a
model thinks their decision was correct. That circular grader is the exact
thing D9 and bite 2 already ruled out.

---

## D-FSRS-3 — `is_due` changes shape (and that's safe): **`due` comes from the card, `now` is injected**

The placeholder `is_due(last_reviewed_iso, now_iso, *, interval_days) -> bool`
becomes card-driven:

```
due_at(card_state) -> datetime          # card_state["due"], parsed
is_due(card_state, now) -> bool         # now >= due_at(card_state)
record_review(card_state | None, outcome, now, *, engagement=None)
        -> new_card_state               # scheduler.review_card(card, grade(...), review_datetime=now)
```

- **`interval_days` is gone** — the interval is now FSRS's output, not an
  input. `is_due` has **no callers today** (it's a placeholder tested in
  isolation), so changing its signature breaks nothing but its own tests. The
  bite-2 docstring's "same-signature drop-in" was optimistic; recording that
  here so the swap isn't a surprise.
- **`now` is always injected**, never read from the wall clock inside the
  module. FSRS's `review_card` will default `review_datetime` to `now()` if
  omitted; we pass it explicitly, matching the fleet's "no ambient
  `Date.now()`" determinism discipline and keeping the tests scriptable
  (bite 2's tests already inject every timestamp).
- **A fresh decision has no card yet** → `record_review(None, ...)` starts a
  `Card()`. A decision with no card is "never reviewed," which for a
  freshly-sealed decision means due immediately — the same thing a fresh
  `Card()`'s `due=now` already says.

---

## D-FSRS-4 — Dependency posture: **soft FSRS, fixed-interval fallback (mirror soft-Nestor)** — *settled 2026-08-11: SOFT*

**Ruling: soft dependency**, the recommended option below. `fsrs` in an
optional extra; when present, real FSRS scheduling; when absent, `is_due` /
`record_review` degrade to a fixed-interval fallback (held grows the interval,
regressed resets it) so the resurface flow never depends on a heavy install —
the same soft-everything posture bite 1 set for Nestor.

Two defensible options; I recommend the first but this is the live fork:

- **(recommended) Soft dependency, like Nestor.** `fsrs` goes in an optional
  extra (`the-forge[fsrs]`). If it's installed, `is_due` is FSRS. If it's
  **not**, scheduling degrades to the current fixed-interval placeholder with a
  one-time warning — the resurface flow itself is unaffected (you can always
  resurface on demand; you just lose "which seals are due"). This matches the
  house's soft-dependency pattern (oakenscrolls-office PR #3, bite 1's
  soft-Nestor) and the store's "no heavy dep required to run a tool" ethos.
  Cost: one fallback path to keep tested.
- **Hard dependency.** `fsrs>=6.3,<7` is a required install; no fallback path.
  Simpler (the reuse-map literally called `pip install fsrs` "the entire
  remaining lift"), and FSRS is tiny and pure-Python. Cost: breaks the
  "soft-everything" symmetry bite 1 just established, and a store tool now
  hard-imports a third-party scheduler.

**Version pin, either way:** `fsrs>=6.3,<7`. FSRS **major** bumps change the
algorithm and default parameters (the same reason the engine caps at `<1.0`) —
`<7` accepts 6.x fixes and refuses a silent algorithm change. `6.3.2` is
current.

---

## What the build looks like once this is settled (for reference, not to approve here)

1. `stores/checkpoint_schedule.py` — the sidecar: `load_card`/`save_card`
   keyed by `(builder_id, decision_type, surface_norm)` under the checkpoint
   root, `Card.to_dict()` as the on-disk shape; `grade`, `record_review`,
   `due_at`, `is_due`; soft-`fsrs` import per D-FSRS-4.
2. Rewire `checkpoint_calibration.is_due` to delegate (or move it there and
   re-export), delete the fixed-interval body.
3. `resurface()` calls `record_review(card, outcome, now)` after a held or
   regressed outcome, persisting the updated card — so the schedule actually
   advances. (Its return type may gain the next `due` date; TBD at build.)
4. Tests: card round-trip, held→interval-grows, regressed→interval-resets,
   `is_due` boundary, soft-`fsrs`-absent fallback, `now` injection determinism.
5. Update `docs/design/the-forge.md`'s bite ladder + the keeping record.

**The only things blocking that build are D-FSRS-1 (settled: sidecar),
D-FSRS-2 (settled: held→Good/regressed→Again, Hard/Easy reserved), D-FSRS-3
(settled: card-driven, injected `now`), and D-FSRS-4 (open: soft vs hard
dependency).** Ruling on D-FSRS-4 unblocks the whole bite.
