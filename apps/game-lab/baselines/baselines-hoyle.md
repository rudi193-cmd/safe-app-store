# Baseline additions — the Book of Hoyle 😅
*Six classic Hoyle card games, official rules fetched & cited, same test as everything else: uniform-random vs all-John, **N=500 each**, every number from a real in-tree run. Engines in `../sims/`; capture in `runlog-added-games.md`. ΔΣ=42.*

## Results (N=500, measured)
| Game | Seats | RANDOM | JOHN | Avg len | Note |
|---|---|---|---|---|---|
| **Cribbage** | 2 | dealer **62.8%** / 37.2% | dealer **51.6%** / 48.4% | 12.6→8.8 hands | **real dealer/crib edge** — the one seat-structural game; ~15% skunks. Sloppy random play makes the crib's guaranteed points relatively more decisive, so the random dealer edge runs higher than John's. |
| **Go Fish** | 2 | 50.4 / 49.6 | 46.8 / 53.2 | 55→51 turns | fair; draws impossible (13 books is odd); slight second-mover lean |
| **Hearts** | 4 | 130·129·120·121 (2.2% tie) | 116·132·127·125 (1.4% tie) | 11 hands | fair, seat-independent |
| **Crazy Eights** | 4 | 127·138·106·105 (4.8% stall) | 141·133·104·100 (4.4% stall) | 31→29 plies | mild earlier-seat lean (opener sheds first in a single hand); random suit-calls stall a touch more |
| **Spades** | 4 (teams) | **100% hit the 300-hand cap, no winner** | 50.2 / 49.8 | 300→13 hands | **random bidding never ends** — team contracts avg ~13 vs ~6.5 real capacity; only John resolves |
| **War** | 2 | 47.6 / 52.4 | ≡ random (decision-free) | ~500→471 flips | pure luck; fair; John = random by construction |

## What the Hoyle batch adds
1. **Cribbage is the one added game with a built-in seat advantage** — the dealer's crib is worth ~5–7 points a game, and it shows under both policies (dealer 51.6% even with John's competent play, 62.8% under random). Structure, not noise.
2. **Spades-random is pathological, like Cheat-random was** — with uniform-random bids, contracts average ~13 tricks against ~6.5 available, scores peg to the −200 floor, and **all 500 games hit the 300-hand cap without anyone reaching 500.** The game literally can't end under random play; only competent (John) bidding lets it resolve (avg 13 hands). A vivid demonstration that some games *require* a floor of skill just to terminate.
3. **War is the cleanest luck reference in the whole suite** — decision-free, fair ~50/50, averaging ~500 flips a game, and John ≡ random by construction.
4. **No John turn-order LOCKS here** (unlike Skull's 100% / Cheat's ~49%): trick-taking and shedding keep the seats symmetric. Only Cribbage's inherent dealer edge and Crazy Eights' mild opener lean survive.

*Provenance: all six built as engines in `../sims/` that follow the official rules (Bicycle / Pagat), citations sealed in `nestor_work/games.db` under `L3-hoyle`; run random+John at N=500 and captured in `runlog-added-games.md` (2026-08-14). Simplifications noted in each engine's docstring (Cribbage's keep-best-4 discard proxy, Spades' nil omitted + 300-hand cap, War's flip cap, Crazy-Eights single-hand scoring). Measured only. ΔΣ=42.*
