# catgrid

A seeded logic grid with one cat in every row, column and colour region and a unique answer, replayed from its moves.

A willow add-on, and it stays in willow: Die-Namic plays it there, pinned by its files' hashes ([../../willow.pin.json](../../willow.pin.json)). Its card, with everything it does and refuses: [catgrid in willow](https://github.com/willow-memory/Willow/tree/c2b5aa41fd31ab53979ea0d891607ded5f6f3f0a/adapters/stdlib/catgrid).

## Playing it

```
python apps/game/games/play.py catgrid --table DIR play --moves A1,B3,C5
python apps/game/games/play.py catgrid --table DIR play --seed "my board" --size 6
python apps/game/games/play.py catgrid --table DIR check
python apps/game/games/play.py catgrid --table DIR play [--seed TEXT]
```

On a box laid by `box/open_table.py`, `--table DIR` plays on its record.

Each move is a row on the record, through the kernel.

## Where it came from

The catgrid app in this store (apps/catgrid), rebuilt on willow's record and seeded stream.
