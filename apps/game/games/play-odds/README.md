# play-odds

Exact odds, as fractions, for a game's dice and tables: what each outcome's chance really is.

A willow add-on, and it stays in willow: Die-Namic plays it there, pinned by its files' hashes ([../../willow.pin.json](../../willow.pin.json)). Its card, with everything it does and refuses: [play-odds in willow](https://github.com/willow-memory/Willow/tree/dd1e406d66d07fd6397e41880da831e74bbe9696/adapters/stdlib/play-odds).

## Playing it

```
python apps/game/games/play.py play-odds 2d6
python apps/game/games/play.py play-odds 1d20+3 --at-least 15
python apps/game/games/play.py play-odds 2d6 --bands 10,7
python apps/game/games/play.py play-odds DICE [--at-least N] [--bands HIGH,LOW]
```

It reads no box: it takes its arguments alone.

It writes nothing: no row, no file.

## Where it came from

Willow-bot's odds: the exact chance of each outcome, as fractions.
