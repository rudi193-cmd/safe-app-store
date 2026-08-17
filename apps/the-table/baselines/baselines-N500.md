# the-table baselines — N=500

*Measured behavior of the three registered games, played through the-table's own
protocol at volume. Every number here traces to a single reproducible run of
[`the_table/baseline.py`](../the_table/baseline.py); nothing is estimated. See
[`PROVENANCE.md`](PROVENANCE.md).*

- **Rounds:** 500 per game, seeds `0..499`
- **Policy:** uniform-random over `legal_moves` each turn
- **Driver:** the same `GameSession` surface the GM loop uses; reads only public
  `result()` / `observe(0).view`
- **Reproduce:** `cd apps/the-table && python3 -m the_table.baseline 500` (byte-identical every run)

## The measured run

```
▸ bureau  (single-seat exploration)
    turns/round: min 12 · median 26 · mean 27.4 · max 67
       enrolled   :  280   56.0%
       voided     :  220   44.0%

▸ crazy_eights  (4-seat card game, hidden info; game-lab's rules)
    turns/round: min 17 · median 53 · mean 54.4 · max 100
    win distribution (turn order):
       seat 0:  119   23.8%
       seat 1:  122   24.4%
       seat 2:  109   21.8%
       seat 3:  117   23.4%
    no winner (stall): 33  (6.6%)

▸ scene  (single-seat narrative dice, 6 beats; apps/game's Engine.roll)
    turns/round: min 6 · median 6 · mean 6.0 · max 6
    beat outcomes across 3000 beats:
       ARCHITECT_ROLL  :   499   16.6%
       SUCCESS_STANDARD:  1963   65.4%
       CHAOS_BURST     :   538   17.9%
    successes per 6-beat scene (0..6): [0, 3, 9, 40, 92, 183, 173]
    debilities/scene: min 0 · median 1 · mean 1.1 · max 5
    scene 'went well' (successes>=chaos): 488  (97.6%)
```

## What the numbers say

**1. Crazy Eights has no stable seat advantage under random play — and that's a
correction.** An exploratory N=300 pass looked like a clean first-seat edge:
seat 0 at 28.7%, declining monotonically to 21.3% by seat 3. At N=500 with clean
per-round seeding it evaporates — 23.8 / 24.4 / 21.8 / 23.4%, all within sampling
noise of a fair 25%, and the monotonic ordering is gone (seat 1 is nominally
highest). A real turn-order effect would persist across samples; this one didn't.
This is game-lab's own headline lesson reproduced on the-table's spine: *sample
size changes answers* — an apparent edge in a smaller sample was noise. Stalls
(no winner) run 6.6%.

**2. bureau's ending bias is real and reproduces: ~56% enrolled / 44% voided.**
Unlike the card game's phantom seat edge, this one holds across both samples
(59/41 at N=300, 56/44 at N=500). Random wandering reaches the "enrolled" ending
(hand the word-napkin to Hanz) meaningfully more often than "voided" (the blank
to Records) — a structural feature of the map, not noise. Every round resolves
(median 26 turns, max 67, zero cap-outs).

**3. The scene tracks its dice theory, with a faint debility drift.** With stats
at the base (2d6+2), `ARCHITECT_ROLL` (≥12) and `CHAOS_BURST` (<7) are each
exactly 1/6 ≈ 16.7% in theory. Measured: architect 16.6% (dead on), chaos 17.9%
(a hair high) — because every chaos burst lowers a stat, tilting the next roll
slightly toward more chaos. A mild downward spiral, visible only in aggregate;
debilities land at a median of 1 per scene.

**Design note the run surfaced (stable across N): the "went well" heuristic is
too soft.** The scene reads `winners=[0]` whenever `successes ≥ chaos`, which
fires **97.6%** of the time (97.7% at N=300). It barely discriminates — if that
read is ever meant to *mean* something, the threshold wants tightening. Recorded
here, not fixed, because the adapter is out of scope for a measurement run.

## Caveats

- **One policy.** These are uniform-random only. game-lab's sharper findings come
  from a second, *competent* policy ("all-John") that exposes structure random
  play hides; the-table has only the random policy today. A competent policy
  could still reveal a Crazy Eights seat effect that random play washes out.
- **Turn counts are the-table's, not game-lab's.** The crazy_eights adapter
  models each forced draw as its own step (so every draw is an auditable ledger
  row), so these `turns/round` numbers are deliberately not comparable to
  game-lab's ply accounting for the same game. Legality is game-lab's; the turn
  granularity is the adapter's.
- **N=500, single seeding scheme.** Firm for the reversals shown; a genuinely
  small effect could still sit under the noise floor at this N.
