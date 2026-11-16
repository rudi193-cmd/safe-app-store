# The Games — Baselines at N=500 (all measured, provenance-checked)
*Authoritative. Every cell traces to a captured run. The core five (chess, checkers, backgammon, Uno, The Ledger) are measured by `../sims/baseline500.py`; the five deduction/bluffing games below are measured by their own engines in `../sims/`, captured in `runlog-added-games.md`. **N=500**, two policies: uniform-random and all-John. ΔΣ=42.*

> **Provenance note.** The deduction-game rows were regenerated from the engine source now in this tree (`../sims/{coup,skull,liars_dice,cheat,werewolf}.py`), superseding earlier values that were produced in ephemeral sandboxes. Unseeded, so seat counts wobble a few percent run-to-run; the structural findings are stable. Five cells were once published without a run behind them (random Liar's Dice/Cheat/Werewolf, John Coup/Skull) and one N=100 "chess-John White advantage" was sampling noise — all corrected, sealed in Nestor under `baseline.correction`, and re-measured here.

## Random (uniform-random-legal) — N=500
| Game | Seats | Win distribution (…draw) | Avg | Note |
|---|---|---|---|---|
| Chess | 2 | 196 · 195 · **109 draw** | 233 plies | random chess ≈ coin-flip + heavy draws |
| Checkers | 2 | 245 · 249 · 6 | 67 moves | 50/50 |
| Backgammon | 2 | 254 · 246 | 93 turns | 309 gammons (61.8%) |
| Uno (1 hand) | 4 | 123 · 135 · 128 · 114 | 49 plies | ~uniform |
| The Ledger | 4 | 120 · 127 · 127 · 126 | 11 seals | ~uniform |
| Coup | 4 | 112 · 114 · 125 · 149 | 10 turns | ~uniform (mild late-seat drift) |
| Skull | 4 | 139 · 123 · 106 · 132 | 9 rounds | ~uniform |
| Liar's Dice | 4 | 113 · 114 · 138 · 135 | 18 rounds | ~uniform |
| Cheat | 4 | 126 · 114 · 117 · 143 | **740 plays** | ~uniform; random Cheat runs enormously long |
| Werewolf | 8 | wolves **75.8%** · village 24.2% | 2.5 cyc | informed minority dominates |

## All-John (identical competent everyman in every seat) — N=500
| Game | Seats | Win distribution (…draw) | Avg | What John exposes |
|---|---|---|---|---|
| Chess | 2 | 75 · 73 · **352 draw** | 123 plies | **Even.** No first-move edge — the N=100 24/10 was noise. Competent symmetric chess mostly draws. |
| Checkers | 2 | 210 · 242 · 48 | 78 moves | slight P2 lean, near-noise |
| Backgammon | 2 | 242 · 258 | 116 turns | even; 228 gammons (45.6%) — John races better |
| Uno (1 hand) | 4 | 143 · 122 · 125 · 110 | 42 plies | mild P1 lean, ~uniform |
| The Ledger | 4 | 119 · 133 · 135 · 113 | 11 seals | ~uniform |
| **Coup** | 4 | **24 · 75 · 182 · 168** (51 caps) | 148 turns | **real turn-order edge to LATER seats** — seat 0 crushed (4.8%), seats 2–3 favored; plus 51/500 honest stalemates (mutual steal/block never reaches 7 coins), which the turn cap records |
| **Skull** | 4 | **0 · 0 · 500 · 0** | 3.0 rounds | **deterministic lock, confirmed** — symmetric caution → minimal safe raises → the third bidder in seat order clinches every round; one seat wins 500/500 in 3 rounds |
| Liar's Dice | 4 | 134 · 132 · 119 · 115 | 18 rounds | ~uniform (mild opener lean) |
| **Cheat** | 4 | **244 · 120 · 63 · 73** | 37 plays | **near-lock (48.8%)** — honest John almost never challenges → the opener sheds fastest and wins |
| **Werewolf** | 8 | wolves 54.8% · **village 45.2%** | 2.7 cyc | coordinated town nearly **doubles** its win rate (24%→45%), but exposing the seer lets wolves hunt her and 2-in-8 still win the majority |

## What the N=500 pass settles
1. **Random play: every symmetric game is fair** — all seat splits sit near 1/n. The only structural random result is **Werewolf ≈76/24** (parity favors the informed minority).
2. **All-John reveals hidden turn-order structure** where it exists: **Skull is a total lock** (one seat 100%), **Cheat a near-lock** (opener ~49%), **Coup a genuine seat edge** (later seats, seat 0 collapses). These are emergent properties of a perfectly symmetric honest strategy, not bugs — the random baseline shows none of them.
3. **The overturned finding:** at N=100, John-chess looked like a 70%-White edge. At **N=500 it's dead even (75/73)** with 70% draws — sampling noise the bigger N caught. The clearest argument in the whole exercise for running 500 over 100.
4. **Werewolf is where competence helps the underdog** — coordinated seer-sharing lifts town from 24% to 45%, but 2-wolves-in-8 still take the majority.

*Provenance: chess/checkers/backgammon/Uno/Ledger by `../sims/baseline500.py`; Coup/Skull/Liar's-Dice/Cheat/Werewolf by `../sims/{game}.py`, captured in `runlog-added-games.md` (2026-08-14). Correction sealed in `nestor_work/games.db` under `baseline.correction`. ΔΣ=42.*
