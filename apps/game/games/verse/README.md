# verse

Verse from the word pairs your own files use most, in your own dialect.

A willow add-on, and it stays in willow: Die-Namic plays it there, pinned by its files' hashes ([../../willow.pin.json](../../willow.pin.json)). Its card, with everything it does and refuses: [verse in willow](https://github.com/willow-memory/Willow/tree/bdf8d3cb62bf3facfb714b38fd439b6b56fb44dd/adapters/stdlib/verse).

## Playing it

```
python apps/game/games/play.py verse --table DIR [--seed TEXT] [--lines N]
```

On a box laid by `box/open_table.py`, `--table DIR` plays on its record.

It writes nothing: no row, no file.
