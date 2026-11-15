# play-checkers

Checkers played on the record: the code holds the rules, and a draw is only the one who holds the key sealing it.

A willow add-on, and it stays in willow: Die-Namic plays it there, pinned by its files' hashes ([../../willow.pin.json](../../willow.pin.json)). Its card, with everything it does and refuses: [play-checkers in willow](https://github.com/willow-memory/Willow/tree/bdf8d3cb62bf3facfb714b38fd439b6b56fb44dd/adapters/stdlib/play-checkers).

## Playing it

```
python apps/game/games/play.py play-checkers --table DIR new
python apps/game/games/play.py play-checkers --table DIR show
python apps/game/games/play.py play-checkers --table DIR move 11-15
python apps/game/games/play.py play-checkers --table DIR resign
```

On a box laid by `box/open_table.py`, `--table DIR` plays on its record.

Each move is a row on the record, through the kernel.

## Where it came from

English draughts, ported from the-table's checkers over game-lab's rules (apps/the-table, apps/game-lab in this store), checked against game-lab's on 22,039 positions. A draw is the game master's seal, never the code's call.
