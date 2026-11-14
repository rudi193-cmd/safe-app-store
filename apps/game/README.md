# game: where Die-Namic is built

The store's playground home for **Die-Namic**: the game side of the house,
the box an AI game master keeps a table in. It starts empty on purpose. The
pieces come over one at a time, each as its own step, and when the build
meets the store's promotion bar it is lifted out into its own repo in the
Die-Namic-Systems org.

## What was here: the first engine

[`archive/first-engine/`](archive/first-engine/) is where Die-Namic's game
master started, kept whole and unedited: Jane GM, a Streamlit table run by
Consus, "your AIGM" (Engine Codex v1.5.0.0, `engine_v1_7.py`), with its
2026-04-08 [code review](archive/first-engine/CODE_REVIEW.md), which found it
could not run as it stood.

Its roll is still load-bearing. The 2d6 + stat read in three bands is what
the-table's `SceneSession` rolls through today (the-table's path to it now
points into the archive), and what willow's game-master add-on rebuilt on
the record as strong, weak and miss. Its one closed door is
`Engine.roll(stat, is_creator=True)`: the creator's roll that always
succeeds, which everything since answered with a seal instead. Both are
proposed in `stores/decisions/proposed.json`.

## What comes here

Each a step of its own, in the order the build needs them:

- **the game box**, now a demo in willow (`demo/game-box` there): a game
  master's binder that can be asked, the record, prep and end-of-night
  stacks, offers at the table, chapters that carry canon, and stories from
  story-timeline;
- **the-table**: the game protocol, the driver, its games and worlds;
- **ai-game-master**: the blueprint, its decisions and its covenant;
- **game-lab**: official rules, simulators and measured baselines.

The pieces willow keeps as add-ons (game-master, checkers, dice, odds and
the rest) stay there, and Die-Namic pins them.
