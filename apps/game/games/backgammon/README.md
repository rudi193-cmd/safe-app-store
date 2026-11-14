# backgammon

Backgammon on the record, every throw dice's own row: the rules held whole, gammons and backgammons scored.

A willow add-on, and it stays in willow: Die-Namic plays it there, pinned by its files' hashes ([../../willow.pin.json](../../willow.pin.json)). Its card, with everything it does and refuses: [backgammon in willow](https://github.com/willow-memory/Willow/tree/9d7c45b0d1ab64e5c07519ec6bbb42489ebb19b1/adapters/stdlib/backgammon).

## Playing it

```
python apps/game/games/play.py backgammon --table DIR new
python apps/game/games/play.py backgammon --table DIR show
python apps/game/games/play.py backgammon --table DIR roll
python apps/game/games/play.py backgammon --table DIR move "24/18 13/11"
python apps/game/games/play.py backgammon --table DIR resign
python apps/game/games/play.py backgammon --table DIR check
```

On a box laid by `box/open_table.py`, `--table DIR` plays on its record.

Each throw is dice's own roll row; each turn a row, through the kernel.

## Where it came from

Backgammon, ported from the-table's backgammon over game-lab's rules (apps/the-table, apps/game-lab in this store), its moves checked against game-lab's on 216,372 positions. A turn uses as many dice as it can, and the larger when only one can, as the game's rules have it.
