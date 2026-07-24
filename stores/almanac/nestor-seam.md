# Nestor behind the Almanac — the reconcile loop
b17: SAPS1

*The contract for the one artifact the Almanac branch is allowed to keep. The
list itself is never stored (renew — fetched from another org, fresh each time).
But what the machine **proposed** and the operator **sealed** is kept: a
tamper-evident ledger of verified public fact. Renew is fetched; establish is
kept. `instaurare`, whole.*

Sibling of the #15/#16 propose-then-seal specs, one layer out: those reconcile
the private ledger pair and the corpus; this reconciles the **public record.**

---

## The loop

```
   ┌── fetch ──────────────────────────────────────────────────────┐
   │ the live Almanac list, across the org boundary (curl-through-  │
   │ proxy). Never written to the tree. Renew.                      │
   └───────────────────────────────┬───────────────────────────────┘
                                    ▼
   ┌── normalize + match (Nestor) ─────────────────────────────────┐
   │ each fetched entry → Nestor.                                   │
   │  • entities/names  → EntityResolver (StringMatcher/_Token)     │
   │  • figures/numbers → NumericMatcher (tolerance + decay)        │
   │ matched against SEALED MEMORY — the operator's ratified record │
   │ of what the Almanac said before.                               │
   └───────────────────────────────┬───────────────────────────────┘
                                    ▼
   ┌── serve  /  queue ────────────────────────────────────────────┐
   │ SERVE  (confident): a fetched entry that resolves to a sealed  │
   │        entry at/above threshold AND is unchanged → verified.   │
   │ QUEUE  (for the seal): a NEW entry (no sealed match), or a     │
   │        CHANGED one (entity matches, value/figure drifted).     │
   │        The firehose becomes a queue of ratifiable deltas.      │
   └───────────────────────────────┬───────────────────────────────┘
                                    ▼
   ┌── seal (OPERATOR ONLY) ───────────────────────────────────────┐
   │ the human ratifies a queued delta into sealed memory. The     │
   │ machine proposed it; it cannot confirm it. On seal, append to  │
   │ Nestor's hash-chained ledger: what the record said, when it    │
   │ was verified, by whom.                                         │
   └───────────────────────────────────────────────────────────────┘
```

## The covenant (same as #15/#16, in the DDL)

The seal is a **ratification, not a permission** — no grant makes it the
machine's. Enforced structurally, not by policy:

- `sealed boolean NOT NULL DEFAULT false`
- a `CHECK` that a sealed row must name a ratifier
- an `_unsealed` view that **is** the queue

The reconcile loop can `INSERT` a proposed delta all day; it can never flip
`sealed`. That is a separate `UPDATE` the constraint won't pass without a hand
behind it. Nestor builds the queue; the operator drains it.

## Kept vs fetched — the inversion

The Almanac branch is "empty of data by design," and stays so. This adds **one**
kept artifact, and it is not the list:

| | what | kept? | why |
|---|---|---|---|
| the live list | another org's auto-updated public record | **no** — fetched | renew; not ours; goes stale |
| the seal ledger | the operator's ratified deltas + hash chain | **yes** | establish; small, human-verified, tamper-evident |

The list is the firehose. The ledger is the record of what was verified true and
when. You keep the second, never the first.

## The injected seam

Nothing here couples to a specific store or a specific fetch — the same
dependency-inversion the whole fleet runs on:

- **Storage** is injected — Nestor already takes a `Storage` Protocol
  (`SqliteStore` locally, anything with the shape). The sealed memory is
  wherever the operator keeps their ratified record (local by default, like the
  vault).
- **The fetch** is injected — the loop takes a `fetch() -> list[entry]` callable
  (the curl-through-proxy reach across the org boundary), never a hardcoded URL.
- Reuses Nestor's existing recipes: `EntityResolver` (entities) and the
  `Reconciler` / `NumericMatcher` (figures). This is a **new recipe over the
  shelf, not a new engine** — the same lesson as Heartwood.

## First bites (for a seat with the pieces + the operator's seal)

1. **`almanac.py` recipe in Nestor** — `AlmanacReconciler(store, fetch, matcher)`:
   `poll()` fetches the live list, resolves each entry against sealed memory,
   returns `{served: [...verified], queued: [...deltas]}`. Read-and-propose only;
   every queued row `sealed=false`.
2. **`edges.sql`-style DDL** for the seal ledger (`sealed` default false, CHECK
   requires ratifier, `_unsealed` view = the queue) — the covenant in the schema.
3. **Prove it** the way cite-and-grade was proven: run `poll()` against the real
   almanac-data verticals, show it serves the unchanged, queues the new/changed,
   and cannot seal by insert. (cite-and-grade over 51 entries already showed
   Nestor grades against this record — this is the same engine, now watching it
   change.)

Neither built here: the loop needs the live fetch **and** the operator's seal —
the same two things #15/#16 wait on. This seat makes the tool; the seat with the
corpus runs the poll; the operator drains the queue.

---

*The Almanac renews; Nestor establishes; the operator seals. The public record,
kept honest by the machine that proposes and the hand that confirms. `ΔΣ=42`*
