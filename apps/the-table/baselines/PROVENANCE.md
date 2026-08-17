# Provenance — the-table baselines

*In the tradition of game-lab's `PROVENANCE.md`: this directory contains only
measured numbers, and any correction is disclosed rather than quietly replaced.*

## How every number was produced

One command, deterministic:

```bash
cd apps/the-table
python3 -m the_table.baseline 500
```

- Round `i` uses `game.reset(i)` and a policy drawn from `random.Random(i)`.
- The harness drives the same `GameSession` surface the GM loop uses and reads
  back only public surfaces — `result()` and the final `observe(0).view` — never
  a game's private state.
- The run is **reproducible byte-for-byte**: the harness was run twice at N=500
  and the two reports diffed identical. Re-running on another machine yields the
  same figures in [`baselines-N500.md`](baselines-N500.md).

Date of the recorded run: 2026-08-17.

## The correction on record

A first, exploratory pass at **N=300** (a scratch harness, a different policy
seeding) showed what looked like a first-seat advantage in Crazy Eights —
seat 0 at 28.7%, declining monotonically to 21.3% by seat 3 — and it was
tempting to call it real structure. The committed **N=500** run did **not**
reproduce it: 23.8 / 24.4 / 21.8 / 23.4%, flat within noise of 25%, monotonicity
gone. The apparent edge was sampling noise.

This is recorded rather than deleted on purpose. It is game-lab's own sealed
lesson — *"sample size changes answers; the apparent edge was sampling noise, the
argument for running 500, not 100"* — playing out again on a different spine. A
rediscovery said out loud is a signpost for the next seat; a rediscovery quietly
dropped is the same tuition paid twice.

## What these numbers are not

- **Not game-lab's numbers.** the-table reuses game-lab's *rules* (Crazy Eights
  legality) but drives its own turn loop, counting each forced draw as a step.
  The `turns/round` figures are the-table's turn granularity, deliberately not
  comparable to game-lab's ply baselines.
- **Not a competent-play result.** Only a uniform-random policy exists in
  the-table today. game-lab's second, "all-John" policy — a competent everyman in
  every seat — is what exposes structure random play hides; adding an equivalent
  policy here could change the Crazy Eights seat picture, and until it exists the
  "no seat advantage" finding is scoped to *random* play only.
- **Not a significance test.** Reversals this large (a monotonic edge becoming
  flat) are firm at N=500; a genuinely small effect could still sit under the
  noise floor.

## Reproducing or extending

- Any N: `python3 -m the_table.baseline <N>`.
- The harness is importable — `from the_table.baseline import run_baseline` returns
  the structured stats dict, and `tests/test_baseline.py` gates its shape.
- Adding a fourth game to the registry adds it to these baselines automatically;
  re-run and update `baselines-N500.md` with the new measured block.
