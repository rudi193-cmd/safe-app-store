# aristarchus

*A decision memory that keeps the lineage **and** the rejections.*

Named for Aristarchus of Samos, whose heliocentric proposal was rejected
around 270 BC with no recorded reason and no reopen condition — so nobody
could tell **never** from **not yet**, and the question stayed sealed shut for
eighteen centuries.

## What this is

The playground test-build of the design at
[Nestor `docs/decision-memory.md`](https://github.com/rudi193-cmd/nestor/blob/master/docs/decision-memory.md)
(the narrative: [`docs/the-fourth-store.md`](../../docs/the-fourth-store.md)).
The finding it tests:

> Git keeps the lineage and throws away the rejections. Nestor keeps the
> rejections — signed, with reasons — and models no lineage.

This build holds both halves, standalone and stdlib-only. **Nothing here
imports Nestor**: the point is to prove (or falsify) the design's mechanics
here, so what goes back to Nestor is evidence-backed core changes (N2–N7),
not speculation.

## The four verbs

| Verb | Mechanism |
|---|---|
| **made** | `propose()` (machine, draft) → `seal()` (human, HMAC-signed, `verifier ≠ author`) — with a `reason` on the yes |
| **rejected** | `reject()` — reason required, signed, durable; `reopen_when` distinguishes *never* from *not yet* |
| **modified** | `supersede()` — the old row keeps its reason and falls out of the live index; a partial unique index keeps one-live-row as a real constraint while history accumulates |
| **affects future** | `constraints_on(question)` — live decision + lineage-with-reasons + rejections-with-reasons + open reopen conditions + graph edges, resolved through a fuzzy Matcher so a re-worded question still finds its record |

Every read re-verifies: a row that merely *says* sealed is surfaced as
tampered, never served. Every write appends to a hash-chained ledger, and a
broken chain stops the store.

## Run it

```bash
pip install -e ".[dev]"
ARISTARCHUS_SEAL_KEY=dev python -m pytest tests/ -q
```

## What this is not, yet

- **Not benched.** The Matcher is the load-bearing joint (N1): if it can't
  recognize the same decision in different words, `constraints_on` returns
  nothing and the system is worse than useless — it is *reassuring*. The
  shipped `StringMatcher` is the dumb baseline; the bench against a semantic
  matcher is the gate before any CI check trusts this (design doc, open
  question 2).
- **Not a gate.** `nestor decision check` (N9) needs the bench first.
- **Not Nestor.** By design, for now.
