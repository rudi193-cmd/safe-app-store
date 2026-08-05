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

## The gate — `aristarchus check` (N9, warn-mode)

```bash
pip install -e ".[semantic]"     # the encoder; string fallback is falsified
ARISTARCHUS_SEAL_KEY=... aristarchus check --db fleet.db --ledger fleet.jsonl \
    "Can the decision gate fail builds fail-closed?"
```

```
  constrained 'Can the decision gate fail builds fail-closed?'
      law: 'no - warn-mode only' (sealed by rudi193; reason: N1 bench: ...)
      rejected: 'strict enforcement now' - bench numbers do not support it
                [not yet - reopen when: larger corpus or stronger encoder ...]
```

The contract the bench earned: **exit 0 always** — it speaks, it does not
block. Questions resolving ≥0.95 report constraints as findings; the
0.85–0.95 band reports "possible match — check." Two things outrank
advisory: a broken ledger chain exits 2 unconditionally, and a row whose
seal fails verification is always surfaced as TAMPERED. `--strict` (exit 2
on findings) exists for experimentation and announces, every run, that the
bench has not earned it.

## The N1 bench — all legs run; the gate opens to advisory, not enforcement

`bench/n1_bench.py` over `bench/corpus.json` (20 stored decisions × 3
paraphrases, 10 near-miss distractors, 10 novel questions), through the real
`constraints_on()` path. Results + provenance in `bench/results/n1.json`
(the fastembed leg ran in a huggingface-reachable environment; this one
denies the host).

| Matcher | Best usable point | Verdict |
|---|---|---|
| `StringMatcher` (difflib) | none — 0% recall @ 0.90; 67% recall costs 80% false-match @ 0.50 | **falsified** |
| `TokenMatcher` (jaccard) | none — strictly worse | **falsified** |
| spaCy `en_core_web_md` (averaged word vectors) | none — 63% recall @ 0.90 costs 60% false-match | **falsified** |
| **fastembed sentence encoder** | **0.90: 88.3% recall / 20% false-match · 0.95: 51.7% / 5%** | **viable band, advisory only** |

Two findings in the fastembed curve worth their weight:

1. **`wrong_key` is 0.0 at every threshold.** When the encoder matches a
   paraphrase, it *never* picks the wrong stored decision — every false
   match comes from intruders (near-miss/novel questions), not from
   cross-wiring two known decisions.
2. **There is a real operating band (0.90–0.95)** — the first matcher with
   one. But its floor is 20% false-match at the recall end, 48% missed
   decisions at the precision end.

**Ruling:** `constraints_on()` with the sentence encoder is fit for
**advisory** use — surfacing constraints to an agent, warn-mode CI — using
Nestor's own serve/queue split: ≥0.95 served as a confident match, 0.85–0.95
surfaced as "possible match — check." It is **not yet fit to fail a build
fail-closed**: a hard gate at 0.90 cries wolf on one question in five, and
one at 0.95 sleeps through half. Enforcement waits on a larger corpus and/or
a stronger encoder — margin is already known-mostly-falsified (Nestor IDEAS
§1.1), so threshold and corpus are the honest knobs.

- **Warn-mode gate (N9) is now unblocked.** Fail-closed is not.
- **Not Nestor.** By design, for now.
