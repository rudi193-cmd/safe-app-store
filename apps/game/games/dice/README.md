# dice

Seeded dice rolls as rows: every roll replayable and checkable.

A willow add-on, and it stays in willow: Die-Namic plays it there, pinned by its files' hashes ([../../willow.pin.json](../../willow.pin.json)). Its card, with everything it does and refuses: [dice in willow](https://github.com/willow-memory/Willow/tree/4b2064071393cef948689ac8fb2badb29faf0a7b/adapters/stdlib/dice).

## Playing it

```
python apps/game/games/play.py dice --table DIR roll 2d6+1
python apps/game/games/play.py dice --table DIR check
python apps/game/games/play.py dice --table DIR roll DICE
```

On a box laid by `box/open_table.py`, `--table DIR` plays on its record.

Each move is a row on the record, through the kernel.

## Where it came from

Willow-bot's seeded stream: every roll a row, thrown again from its seed to check it.
