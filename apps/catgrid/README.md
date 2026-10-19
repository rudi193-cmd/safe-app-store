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

## The rules

| # | Rule |
|---|---|
| R1 | A move names a cell on the board (`A1`, `B3`: cross-table addresses) |
| R2 | `cat <cell>` where the answer has a cat: it stays |
| R3 | A wrong cat costs a heart and is not placed (every rule-breaking cat is wrong, because the one answer breaks none) |
| R4 | `x <cell>` marks "no cat here", free; `clear <cell>` takes it back |
| R5 | Nothing goes on a cat; no clearing what isn't marked |
| R6 | Three hearts; at none the game is lost |
| R7 | All n cats placed: won |
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
