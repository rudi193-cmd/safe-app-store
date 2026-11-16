# play-life

Conway's Game of Life as rows: a fully deterministic world on the record.

A willow add-on, and it stays in willow: Die-Namic plays it there, pinned by its files' hashes ([../../willow.pin.json](../../willow.pin.json)). Its card, with everything it does and refuses: [play-life in willow](https://github.com/willow-memory/Willow/tree/dd1e406d66d07fd6397e41880da831e74bbe9696/adapters/stdlib/play-life).

## Playing it

```
python apps/game/games/play.py play-life --table DIR play
python apps/game/games/play.py play-life --table DIR play --seed "my soup" --size 20 --generations 200
python apps/game/games/play.py play-life --table DIR check
python apps/game/games/play.py play-life --table DIR play [--seed TEXT] [--size N]
```

On a box laid by `box/open_table.py`, `--table DIR` plays on its record.

Each move is a row on the record, through the kernel.
