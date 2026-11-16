# play-tarot

A seeded tarot draw on the record, replayable by anyone with the seed.

A willow add-on, and it stays in willow: Die-Namic plays it there, pinned by its files' hashes ([../../willow.pin.json](../../willow.pin.json)). Its card, with everything it does and refuses: [play-tarot in willow](https://github.com/willow-memory/Willow/tree/dd1e406d66d07fd6397e41880da831e74bbe9696/adapters/stdlib/play-tarot).

## Playing it

```
python apps/game/games/play.py play-tarot --table DIR draw [N]
python apps/game/games/play.py play-tarot --table DIR check
```

On a box laid by `box/open_table.py`, `--table DIR` plays on its record.

Each move is a row on the record, through the kernel.

## Where it came from

Willow-bot's seeded draw; oracle-text and pile-poetry deal from the same stream.
