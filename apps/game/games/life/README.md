# life

Conway's Game of Life as rows: a fully deterministic world on the record.

A willow add-on, and it stays in willow: Die-Namic plays it there, pinned by its files' hashes ([../../willow.pin.json](../../willow.pin.json)). Its card, with everything it does and refuses: [life in willow](https://github.com/willow-memory/Willow/tree/4b2064071393cef948689ac8fb2badb29faf0a7b/adapters/stdlib/life).

## Playing it

```
python apps/game/games/play.py life --table DIR play
python apps/game/games/play.py life --table DIR play --seed "my soup" --size 20 --generations 200
python apps/game/games/play.py life --table DIR check
python apps/game/games/play.py life --table DIR play [--seed TEXT] [--size N]
```

On a box laid by `box/open_table.py`, `--table DIR` plays on its record.

Each move is a row on the record, through the kernel.
