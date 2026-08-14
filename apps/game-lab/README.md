# game-lab — rulesets, reference simulators, and baselines
*A companion to `apps/ai-game-master`: the games that engine can run, with **official cited rules**, self-play reference simulators, and a **null-model baseline** for each. Built to the same covenant as the fleet — every number here traces to a real run; nothing is estimated.*

## Layout
- `rules/` — official rules, fetched from authoritative sources (Bicycle / Pagat / FIDE / WOTC SRD / Mattel) and cited inline. `COMPENDIUM.md` covers the board classics, the bluffing/deduction family, D&D 5e (shape + gap), and make-believe; `uno-official.md` is the Uno correction (official vs house, tagged).
- `sims/` — self-play simulators, each runnable under two policies: **uniform-random** and **all-John** (an identical competent everyman in every seat). The core five (chess, checkers, backgammon, Uno, The Ledger) run through `baseline_core.py` / `john_baseline.py` / `baseline500.py`. The eleven added games have their own self-contained engines — `coup.py`, `skull.py`, `liars_dice.py`, `cheat.py`, `werewolf.py`, `cribbage.py`, `go_fish.py`, `hearts.py`, `crazy_eights.py`, `spades.py`, `war.py` — driven by `run_added_games.py`.
- `baselines/` — measured results at **N=500** per game per policy: `baselines-N500.md` (core suite + five deduction/bluffing games) and `baselines-hoyle.md` (six Book-of-Hoyle additions). `runlog-added-games.md` is the dated in-tree capture the added-game rows trace to.

## Two headline findings
- **Random hides structure; all-John reveals it.** Symmetric games look fair under random seats, but an identical *competent* policy exposes hidden turn-order structure — a total lock in Skull (one seat 100%) and near-lock in Cheat (opener ~49%), a real dealer edge in Cribbage (dealer ~52% even under competent play), a later-seat edge plus honest stalemates in Coup, and games that *cannot terminate* under random play (Spades: all 500 random games hit the hand-cap; only competent bidding resolves).
- **Sample size changes answers.** At N=100 all-John chess looked like a 70% White advantage; at N=500 it is dead even (75/73, 70% draws). The apparent edge was sampling noise — the argument for running 500, not 100.

## Provenance & honesty note
See `baselines/PROVENANCE.md`. During development, some agent-produced rows were mistakenly published before being run; all were caught, disclosed, and replaced with measured values, and the correction is sealed in the fleet's Nestor game-rules store. This directory contains only measured numbers.
