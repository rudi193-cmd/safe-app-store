# Convention — tombstones carry a forwarding pointer

*What an archived catalog entry must say, so that what was known about a build
survives the build moving.*

**Implements** [`CLAUDE.md`](../../CLAUDE.md) §4 — *archive, don't delete.*

---

## The gap this closes

`CLAUDE.md` §4 is already right: stale builds get `status: archived` in the
catalog and are never removed. The record survives.

But **the record surviving is not the same as the knowledge surviving.**
`tools/catalog_lint.py` rule 4 states it plainly:

> *an entry may omit `path` only when it is archived*

So the single state in which a build's code has moved is the single state
permitted to point nowhere. Nothing in the catalog, the keeping record, or any
lint asks **where it went**.

The failure that follows is quiet and nobody chooses it. An app is absorbed into
a larger one. The code travels. The documents describing its open defects — a
safety finding, a legal exposure, a critical bug — describe a path that no
longer exists, attached to an `app_id` now marked `archived`. Nobody decided to
drop the finding. It simply wasn't attached to anything that moved.

That is the same shape as every other failure this repo has mechanised away: a
thing a person has to remember, enforced against whoever is tired and in a
hurry.

---

## The rule

**Every archived entry records why it ended and where its code went.**

An archive has these end-shapes, and each has a required forward:

| End-shape | Meaning | Required forward |
|---|---|---|
| **merged** | The code was absorbed into another build | `successor` — the `app_id` it became part of. The forward is **mandatory**; a merge with nowhere to point is a deletion wearing an archive. |
| **promoted** | It left the playground for its own repo | `successor` — the repo URL. This is the good ending; `stores/{major}/promoted/<app_id>.json` already holds the verdict, and the tombstone points at it. |
| **rebuilt** | It was replaced by a fresh implementation; **the code does not travel, the knowledge does** | `successor` — the build that replaces it, plus a `carried` list that is the whole point. Proposed 2026-08-04 for `law-gazelle` → `homestead-law`; see [`docs/homestead-law-build-plan.md`](../homestead-law-build-plan.md). **Not yet ratified.** |
| **retired** | It ended, and nothing carries it forward | `reason` — a sentence saying what was decided. This is the only shape permitted to have no successor, and it must say so deliberately rather than by omission. |

**`retired` is the only one that may point nowhere, and it must say why.** The
distinction that matters is between *nothing carries this forward* and *nobody
recorded what did.* Those look identical in a catalog today.

## What travels with the code

When an entry is archived as **merged** or **promoted**, its open findings go
with it — they are properties of the code, not of the directory it used to sit
in. Before archiving:

1. **List what is open** — bugs, safety findings, legal exposures, unresolved
   decisions — with the documents that hold them.
2. **Re-anchor them** to the successor. A finding whose only address is
   `apps/<gone>/foo.py:52` is already lost.
3. **Record the carry in the tombstone**, so the next reader can see that the
   handover happened and what it contained.

A tombstone with an empty carry list is a claim that nothing was outstanding.
That is a fine thing to claim and a bad thing to imply by silence.

## Shape

Proposed fields on the archived entry, alongside the existing
`seeded | building | gated | stalled | archived` vocabulary that
`catalog_lint.py:108` already enforces:

```json
{
  "id": "example-app",
  "status": "archived",
  "ended": "merged",
  "successor": "bigger-app",
  "reason": "Absorbed as the import module; standalone surface had no users.",
  "carried": [
    "docs/store_minors_safety.md#example-app — export includes living persons"
  ]
}
```

`ended` is a closed enum — `merged | promoted | rebuilt | retired` — for the same reason
`status` is: *never invented, same discipline as the status vocabulary.*

---

## Enforcement — deferred, and where it goes

The durable version is a lint, not a habit. `tools/catalog_lint.py` already
walks every entry, already enforces a closed `VALID_STATES` set, and already has
the rule that lets archived entries omit `path` — so it is the natural place to
add: *an archived entry must carry `ended`; if `ended` is `merged` or
`promoted`, `successor` must be present and must resolve.*

**Deferred by decision (2026-08-04):** the portfolio is mid-reshuffle — some
builds will merge, some will promote, and the shape is not yet known. A lint
written against a vocabulary that has not settled would be enforcing a guess.
It goes in once the first real tombstone is written, and the first tombstone is
the thing that tells us whether these shapes are the right ones. **It already
did:** `law-gazelle` → `homestead-law` is a rebuild — the code does not travel —
and `merged | promoted | retired` had no shape for it. `rebuilt` was added the
same day this convention was written, which is the argument for deferring the
lint rather than against it.

Until then this is a convention, which means it holds only as long as someone
remembers it. That is stated plainly rather than hoped away.

---

## Related

- [`CLAUDE.md`](../../CLAUDE.md) §4 — archive, don't delete
- [`tools/catalog_lint.py`](../../tools/catalog_lint.py) — the status vocabulary, and rule 4
- [`docs/conventions/pinned-dependency-seams.md`](pinned-dependency-seams.md) — the same deferred-enforcement pattern, for the same reason
- [`docs/store_minors_safety.md`](../store_minors_safety.md) — findings that would be lost in an unforwarded merge
- [`stores/README.md`](../../stores/README.md) — the promoted tier a `promoted` tombstone points into

ΔΣ=42
