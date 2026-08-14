# Run log — the eleven added engines, captured in-tree

*Canonical capture. Every number in `baselines-N500.md` (the five deduction/bluffing
games) and `baselines-hoyle.md` (the six Hoyle games) traces to this run — produced
by the engine source in `../sims/`, executed in this repository tree, N=500 per
policy, unseeded. Reproduce with `python3 ../sims/run_added_games.py`.*

Captured 2026-08-14. These numbers **supersede** the earlier values that were
produced in ephemeral research sandboxes (now reclaimed); the source that made
them lives beside this file, so the runs are re-derivable rather than trusted.
Unseeded runs wobble a few percent per seat run-to-run; the structural findings
(Skull lock, Cheat near-lock, Coup seat-skew, Werewolf 76/24, Cribbage dealer
edge, Spades non-termination, War coin-flip) are stable.

## Deduction / bluffing (feeds baselines-N500.md)

```
coup        random  112 · 114 · 125 · 149      avg 9.98 turns    0 caps
coup        john     24 ·  75 · 182 · 168      avg 147.89 turns  51 caps (10.2%)
skull       random  139 · 123 · 106 · 132      avg 9.45 rounds   0 caps
skull       john      0 ·   0 · 500 ·   0      avg 3.00 rounds   0 caps
liars_dice  random  113 · 114 · 138 · 135      avg 17.95 rounds  0 caps
liars_dice  john    134 · 132 · 119 · 115      avg 17.64 rounds  0 caps
cheat       random  126 · 114 · 117 · 143      avg 740.31 plays  0 caps
cheat       john    244 · 120 ·  63 ·  73      avg 37.13 plays   0 caps
werewolf    random  wolves 75.8% · village 24.2%   avg 2.49 cycles
werewolf    john    wolves 54.8% · village 45.2%   avg 2.65 cycles
```

## Book of Hoyle (feeds baselines-hoyle.md)

```
cribbage    random  dealer 62.8% / 37.2%   avg 12.59 hands   skunk 15.2%
cribbage    john    dealer 51.6% / 48.4%   avg  8.84 hands   skunk 15.2%
go_fish     random  50.4 / 49.6            avg 55.35 turns
go_fish     john    46.8 / 53.2            avg 51.05 turns
hearts      random  130 · 129 · 120 · 121  tie 2.2%   avg 11.34 hands
hearts      john    116 · 132 · 127 · 125  tie 1.4%   avg 10.87 hands
crazy_eights random 127 · 138 · 106 · 105  stall 4.8% avg 30.78 plies
crazy_eights john   141 · 133 · 104 · 100  stall 4.4% avg 29.06 plies
spades      random  team1 0 / team2 0      100% hit 300-hand cap (no winner)
spades      john    50.2 / 49.8            avg 13.10 hands   0 caps
war         random  238 / 262             avg 501.41 flips
war         john    252 / 248             avg 470.95 flips  (john ≡ random)
```
