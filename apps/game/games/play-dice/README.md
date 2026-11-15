# play-dice

Seeded dice rolls as rows: every roll replayable and checkable.

A willow add-on, and it stays in willow: Die-Namic plays it there, pinned by its files' hashes ([../../willow.pin.json](../../willow.pin.json)). Its card, with everything it does and refuses: [play-dice in willow](https://github.com/willow-memory/Willow/tree/bdf8d3cb62bf3facfb714b38fd439b6b56fb44dd/adapters/stdlib/play-dice).

## Playing it

```
python apps/game/games/play.py play-dice --table DIR roll 2d6+1
python apps/game/games/play.py play-dice --table DIR check
python apps/game/games/play.py play-dice --table DIR roll DICE
```

On a box laid by `box/open_table.py`, `--table DIR` plays on its record.

Each move is a row on the record, through the kernel.

## Where it came from

Willow-bot's seeded stream: every roll a row, thrown again from its seed to check it.
