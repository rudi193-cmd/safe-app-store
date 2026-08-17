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
| `monte_carlo.py` | Runs the whole adventure at volume (default 500 seeded rounds) for three level-3 pregens side by side, and reports where the average rolls out — per-beat success rates, successes-per-run distribution, the "night held together" verdict, and the one beat no policy can resolve. |
| `gm5e.py` | A live 5e roller CLI (checks, saves, attacks, damage) that appends every roll to a hash-chained ai-game-master ledger the moment it happens. Refuses to record a seal under any machine-flavored name. |
| `sealed_run.py` | One live playthrough to Maunder's question, then the full seal loop: the machine's seal attempt **refused**, a named human's seal **recorded**, the chain **verified**, and a tampered copy **rejected**. |

## Run it

```sh
python3 monte_carlo.py 500          # the side-by-side baseline
python3 gm5e.py open "Aetheris"     # provision a live campaign box
python3 gm5e.py check Aether 5 13 --adv "attune to the broadcast"
python3 sealed_run.py "Ada Vane" SEALED   # a full playthrough + seal + tamper test
```

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
