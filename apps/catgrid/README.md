# catgrid — a seeded logic grid that plays on the table

One cat in every row, every column and every region; no two cats touch, not
even diagonally. The Queens / Star Battle family, after the operator's
Meowdoku, without the ads. Stdlib only, Python 3.11+.

```sh
python3 -m unittest discover -s tests -t .   # from apps/catgrid/
python3 -m catgrid.play 7 6                  # play seed 7, 6x6, in a terminal
python3 -m the_table.proof                   # from apps/the-table/: catgrid on the table
```

## Deterministic

A board is `generate(seed, n)` and nothing else. Same seed, same board, same
bytes (`Board.digest()`), and exactly one answer, checked by search before it is
handed out. A game is its inputs: `(seed, n, moves)` replays to every state,
heart, hint and napkin. The global `random` is never touched; the generator is
bureau's specified xorshift32, so a browser port can make the same board.

| Step | How |
|---|---|
| Placement | a cat per row and column, no two touching, columns tried in a seeded order |
| Regions | each cat grows its own region one neighbouring cell at a time, region and cell drawn from the seed |
| One answer | while a second answer exists, one of its cells moves to a neighbouring region (old region kept connected); a board still with two is never handed out |
| Sizes | 2x2 and 3x3 refuse: their cats can't avoid touching |

## Levels

The same rules with k cats in every row, column and region (the operator: "2
and 3 cats per color ... intermediate levels"):

| Level | Cats a row | Sizes | Why those sizes |
|---|---|---|---|
| 1 | 1 | 1, 4–9 | 2x2 and 3x3 have no placement |
| 2 | 2 | 8–10 | no 2-cat placement below 8x8 (exhaustive search) |
| 3 | 3 | 12–13 | none below 12x12; 14x14 took 78 s to place once in plain Python |

```sh
python3 -m catgrid.play 7 8 2     # seed 7, 8x8, two cats a row
python3 -m catgrid.play 7 12 3    # seed 7, 12x12, three
```

A k-cat board grows its regions from n of its cats: a region still short of k
grows toward the nearest cat nobody holds, then takes the cells left. A 1-cat
board's bytes are what they always were, so older records replay unchanged.
Boards are memoised: `generate` is a pure function with a frozen result.
On the table: `catgrid` (6x6), `catgrid_2cat` (9x9), `catgrid_3cat` (13x13).
Not the smallest sizes: 8x8 with 2 cats and 12x12 with 3 each have only 2
rule-keeping arrangements (mirror images), so every board there shares one of
two answers; 9x9 has 664 and 13x13 42,732.

## Difficulty, measured

`catgrid/rating.py` reasons over a board the way a player does, without the
answer: two plain rules (a cat rules out its neighbours and its full lines; a
line with exactly as many open cells as cats it needs fills them), then a
look-ahead rule (a cell is out when a cat there, followed through, breaks a
rule). `tier(board)` names a board `plain`, `ahead` or `beyond` by the least
reasoning that solves it. `measure(n, k)` also plays each board with a random
player and a careful one. Over 50 boards a level (`baselines/difficulty-N50.md`):

| Level | Look-ahead solves | Careful player wins | Hearts left |
|---|---|---|---|
| 5x5, 6x6, 8x8, 1 cat | 100% | 100% | 3 |
| 9x9, 2 cats | 50% | 92% | 2.58 |
| 10x10, 2 cats | 36% | 76% | 2.08 |
| 13x13, 3 cats | 16% | 60% | 1.44 |

A random player wins none of the 300. The table's baseline
(`the_table/baseline.py`) counts each catgrid round solved, out of hearts, or
at the cap.

## The daily board

`catgrid/daily.py`: one board a day, seeded by the drand round current at that
day's 00:00 UTC. Nobody knows that randomness before the round fires, so no
one can pick an easy day or hand the board out early; anyone can check a day's
board from the round alone. The seed is SHA-256's first four bytes over the
randomness. A `catgrid_games` record of a daily game carries its stamp
(round, randomness, seed), and `soil.replay` refuses one whose seed isn't its
round's. Said, not hidden: the beacon's BLS signature is not checked, and a
beacon that can't be read gives no board (there is no fallback seed). On the
table a daily board is a seed like any other: `reset(stamp["seed"])`.

```sh
python3 -m catgrid.daily 2026-10-19
```

The chain, genesis and period are restated from willow-bot's
`onescript/beacon.py`; `tests/test_daily.py` compares them when willow-bot is
beside this repo.

## The rules

| # | Rule |
|---|---|
| R1 | A move names a cell on the board (`A1`, `B3`: cross-table addresses) |
| R2 | `cat <cell>` where the answer has a cat: it stays (k per row, column and region) |
| R3 | A wrong cat costs a heart and is not placed (every rule-breaking cat is wrong, because the one answer breaks none) |
| R4 | `x <cell>` marks "no cat here", free; `clear <cell>` takes it back |
| R5 | Nothing goes on a cat; no clearing what isn't marked |
| R6 | Three hearts; at none the game is lost |
| R7 | All n x k cats placed: won |
| R8 | Nothing moves after the end |
| R9 | `hint` places one sure cat, never costs a heart; one free per board, more from trivia |
| R10 | `trivia` asks a Jeles question drawn from the seed, one at a time |
| R11 | `answer A..D`: right earns a hint, wrong costs nothing |
| R12 | Marking x on the cell a napkin hides under finds it, once |

## Trivia and napkins

- **Trivia** is Jeles's research corpus (`Jeles/corpus/seed`, or `$CATGRID_JELES`):
  every question that cites a source URL. These are Jeles's *asserted* nuggets,
  sourced but not yet checked by a named human, and the view says so.
- **Napkins** are Gerald's napkin words (`apps/UTETY-Reddit-Bots/gerald-bot/src/data/napkins.json`,
  or `$CATGRID_NAPKINS`). About one board in three hides one under a cell with no cat.
- Either missing is `unavailable`, with why, in the view; the board plays the same.

## The lane (SOIL)

`store_scope` is exactly `catgrid_games`, `catgrid_napkins`, `catgrid_trivia`.
`catgrid/soil.py` writes a game's inputs and outcome, each napkin found and each
question asked, through the injected `libs/storage-backend` seam; with no
backend nothing is written and it says so. `soil.replay(record)` plays a game
back and refuses a record whose board, bank or napkins aren't the ones it names.
The engine (`board`, `solve`, `play`) never imports storage.

## On the table

`apps/the-table/the_table/catgrid_adapter.py` wraps `catgrid.play.Game` as a
`GameSession`, and `registry.py` registers it as `catgrid` (6x6). The table's
proof drives it through the same GM loop as bureau, Crazy Eights and the scene,
into the same tamper-evident ledger.

## Made of the house's pieces

| Piece | From |
|---|---|
| xorshift32 and why it is specified | `apps/bureau/bureau/rng.py` (ported; `tests/test_rng.py` compares every draw) |
| Cell addresses | willows-grove `templates/cross-table/README.md` |
| The game shape and its guard tests | `apps/the-table` |
| Trivia | Jeles `corpus/seed` |
| Easter eggs | Gerald's napkins, `apps/UTETY-Reddit-Bots/gerald-bot` |
| The lane | `libs/storage-backend`, willow-mcp's `store_scope` gate |

The browser port (a JS engine, a differential test against this one, one HTML
page) is the next bite, on bureau's pattern; the APK wraps that page.
