# pile-poetry

Verse from the word pairs your own files use most, in your own dialect.

A willow add-on, and it stays in willow: Die-Namic plays it there, pinned by its files' hashes ([../../willow.pin.json](../../willow.pin.json)). Its card, with everything it does and refuses: [pile-poetry in willow](https://github.com/willow-memory/Willow/tree/c2b5aa41fd31ab53979ea0d891607ded5f6f3f0a/adapters/stdlib/pile-poetry).

## Playing it

```
python apps/game/games/play.py pile-poetry --table DIR [--seed TEXT] [--lines N]
```

On a box laid by `box/open_table.py`, `--table DIR` plays on its record.

It writes nothing: no row, no file.
