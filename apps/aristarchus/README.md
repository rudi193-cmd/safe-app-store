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

## The N1 bench — run, and the gate stays closed

`bench/n1_bench.py` over `bench/corpus.json` (20 stored decisions × 3
paraphrases, 10 near-miss distractors, 10 novel questions), through the real
`constraints_on()` path. Results in `bench/results/n1.json`:

| Matcher | Best usable point | Verdict |
|---|---|---|
| `StringMatcher` (difflib) | none — 0% recall @ 0.90; 67% recall costs 80% false-match @ 0.50 | **falsified** |
| `TokenMatcher` (jaccard) | none — strictly worse | **falsified** |
| spaCy `en_core_web_md` (averaged word vectors) | none — 63% recall @ 0.90 costs **60% false-match**; 100% false-match below that | **falsified** |
| fastembed sentence encoder (the design's intended matcher) | — | **unbenched: huggingface.co policy-denied in this environment** |

The failure mode is exactly the one the design doc predicted: every matcher
runnable here is either blind (string) or *reassuring* (averaged vectors
false-match near-topical questions at rates that would confidently serve
wrong constraints). **So `constraints_on()` must not back any gate yet.**
The sentence-encoder bench is still owed, from an environment that can reach
the model.

- **Not a gate.** `nestor decision check` (N9) waits on the sentence-encoder
  number.
- **Not Nestor.** By design, for now.
