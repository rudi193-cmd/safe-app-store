# Provenance & corrections
Every cell in the baseline tables traces to a captured self-play run: the core five (chess, checkers, backgammon, Uno, The Ledger) by the scripts in `../sims/`; the deduction/bluffing and Hoyle games by subagents that fetched official rules and ran the same protocol.

## What source is in this PR
The `../sims/` directory carries the source for **every** engine and both player policies. The core five (chess, checkers, backgammon, Uno, The Ledger) run through `baseline_core.py` (uniform-random-legal), `john_baseline.py` (the identical "John" everyman), and `baseline500.py` (the N=500 driver). The eleven added games each have their own self-contained engine — `coup.py`, `skull.py`, `liars_dice.py`, `cheat.py`, `werewolf.py`, `cribbage.py`, `go_fish.py`, `hearts.py`, `crazy_eights.py`, `spades.py`, `war.py` — with `run_added_games.py` as their one-shot driver. Each of the eleven was originally prototyped in an ephemeral research sandbox; those sandboxes were reclaimed, so the engines were **rebuilt into this tree and re-run here**, and the numbers in `baselines-N500.md` / `baselines-hoyle.md` now trace to that in-tree run, logged with a date in `runlog-added-games.md`. Nothing here depends on a vanished sandbox: `python3 sims/run_added_games.py` regenerates the added-game rows, `python3 sims/baseline500.py` the core five.

## Corrections made during development (disclosed, not hidden)
1. Three random rows (Liar's Dice, Cheat, Werewolf) were first published without being run — retracted and re-measured. The fabricated Cheat length (~57 plays) was wrong; the real value is ~764.
2. Two John rows (Coup, Skull) were likewise published before being run — retracted and re-measured at N=500.
3. The N=100 "all-John chess White advantage" (24/10) was sampling noise; at N=500 it is even (75/73/352 draws).

The correction is sealed in the fleet Nestor store (`baseline.correction`), and the official Hoyle rulesets are sealed under `L3-hoyle`. Rule of the road here, enforced not promised: **no number ships without a captured run behind it.**
