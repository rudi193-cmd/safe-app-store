# play-dice5e

Full tabletop dice notation (4d6kh3, advantage), rolled on the record and checkable like dice.

A willow add-on, and it stays in willow: Die-Namic plays it there, pinned by its files' hashes ([../../willow.pin.json](../../willow.pin.json)). Its card, with everything it does and refuses: [play-dice5e in willow](https://github.com/willow-memory/Willow/tree/bdf8d3cb62bf3facfb714b38fd439b6b56fb44dd/adapters/stdlib/play-dice5e).

## Playing it

```
python apps/game/games/play.py play-dice5e --table DIR roll 4d6kh3
python apps/game/games/play.py play-dice5e --table DIR roll adv+5
python apps/game/games/play.py play-dice5e --table DIR check
python apps/game/games/play.py play-dice5e --table DIR roll DICE
```

On a box laid by `box/open_table.py`, `--table DIR` plays on its record.

Each move is a row on the record, through the kernel.
