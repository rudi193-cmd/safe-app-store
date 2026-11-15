# play-quiz

A quiz from your own files: a passage with a word missing, and you fill it in.

A willow add-on, and it stays in willow: Die-Namic plays it there, pinned by its files' hashes ([../../willow.pin.json](../../willow.pin.json)). Its card, with everything it does and refuses: [play-quiz in willow](https://github.com/willow-memory/Willow/tree/bdf8d3cb62bf3facfb714b38fd439b6b56fb44dd/adapters/stdlib/play-quiz).

## Playing it

```
python apps/game/games/play.py play-quiz --table DIR ask
python apps/game/games/play.py play-quiz --table DIR answer WORD
```

On a box laid by `box/open_table.py`, `--table DIR` plays on its record.

Each move is a row on the record, through the kernel.
