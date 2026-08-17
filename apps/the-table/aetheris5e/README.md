# aetheris5e — a D&D 5e lens over the Aetheris world

A companion harness that runs [`the-table`](../)'s `worlds/aetheris.json`
under **real 5e dice** (d20 + modifier vs DC, advantage/disadvantage, degrees of
success, the setting's aether-wild zone rule) instead of the-table's native 2d6
`StorySession` engine.

**The world is shared; only the resolution math differs.** Scenes, beats, the
cast, and — above all — Maunder's personhood *decision beat* all come from the
one authored world file. This directory never touches the-table's own engine,
registry, or tests; it imports only the tamper-evident `LedgerSink` as a
consumer.

The one covenant is identical to the-table's and to `apps/ai-game-master`'s:

> **The machine proposes, rolls, and remembers. It never seals. A named human
> at the head of the table seals canon.**

## What's here

| File | What it does |
|------|--------------|
| `dice5e.py` | The dice seam. Delegates **all** randomness and dice-notation parsing to the MIT-licensed [`dice`](https://pypi.org/project/dice/) library (borntyping/python-dice) instead of a hand-rolled parser — the reuse-vs-build wall from `apps/ai-game-master/docs/DECISION.md`. Injects the engine's own `random.Random`, so seeded fights stay reproducible and the global `random` is never touched. |
| `monte_carlo.py` | Runs the whole adventure at volume (default 500 seeded rounds) for three level-3 pregens side by side, and reports where the average rolls out — per-beat success rates, successes-per-run distribution, the "night held together" verdict, and the one beat no policy can resolve. |
| `gm5e.py` | A live 5e roller CLI (checks, saves, attacks, damage) that appends every roll to a hash-chained ai-game-master ledger the moment it happens. Refuses to record a seal under any machine-flavored name. |
| `sealed_run.py` | One live playthrough to Maunder's question, then the full seal loop: the machine's seal attempt **refused**, a named human's seal **recorded**, the chain **verified**, and a tampered copy **rejected**. |
| `statblocks.py` | The campaign's six stat blocks (Aether Construct, Mind-Forge Warden, Tide-Touched Scout, Engine-Blooded Bruiser, Scorched Belt Raider, Concord Enforcer) plus the three level-3 pregens as combat sheets, and four named encounters. Each is a fresh-object factory. |
| `combat.py` | A real 5e combat engine over those stat blocks: initiative, multiattack, attack-vs-AC with crits, typed **damage resistance** (the Bruiser halves force, the Warden halves nonmagical weapons), recharge/AoE specials (Override Pulse stun, Aether Discharge, Salt Spray blind), Overheat, Sneak Attack, Action Surge + a superiority die. Every swing is ledger-logged; `sim` runs the encounter at volume for balance. |
| `test_combat.py` | Locks the engine (14 tests) — resistances, stun-skips-turn, dead-don't-act, seeded reproducibility, and the forbidden act: a **tampered combat log refuses to verify**. |

## Run it

```sh
pip install -r requirements.txt     # the MIT `dice` library (the only dep)

python3 monte_carlo.py 500          # the skill-check baseline
python3 gm5e.py open "Aetheris"     # provision a live campaign box
python3 gm5e.py check Aether 5 13 --adv "attune to the broadcast"
python3 sealed_run.py "Ada Vane" SEALED   # a full playthrough + seal + tamper test

python3 combat.py list                    # the four encounters
python3 combat.py fight warden --seed 3   # one logged fight, round by round + tamper test
python3 combat.py sim enforcers 500       # where a fight rolls out, at volume
python3 -m unittest test_combat           # the engine's own tests
```

### Combat, ledger-logged

`combat.py` extends the harness from skill checks to full initiative combat.
The machine rolls initiative, attacks, saves, and damage, and **remembers**
every swing in a tamper-evident chain (`fight` verifies the log, then rewrites
one hit in a copy and watches the verifier refuse) — it still never seals
anything. The engine owns its own `random.Random`, so a seeded fight (and a
`sim` sweep) is reproducible. Measured at N=500 the four shipped encounters
land from a stomp (raiders) through a coin-flip boss (the Warden) to
action-economy meat-grinders (enforcers, bruiser) — an honest read for a
healerless level-3 party with no death saves, not a tuned one.

## Data stays home

Ledger boxes hold played rolls, human seals, and real names — that is **data**,
not blueprint. Every box is written under `_boxes/` and is `.gitignore`d, the
same wall `apps/ai-game-master` draws between the repo (how to build the vault)
and the box (the campaign that stays home). Nothing in this directory commits a
played campaign.

## Why two engines over one world

the-table's `StorySession` is a PbtA-style 2d6 spine; this is a d20 5e spine.
Pointing both at the same `worlds/aetheris.json` is the point: the *world* — its
scenes, its cast, and the human-only seal that decides what a mind **is** —
outlives whichever dice you bring to the table.
