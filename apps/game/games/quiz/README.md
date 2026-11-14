# quiz

A quiz from your own files: a passage with a word missing, and you fill it in.

A willow add-on, and it stays in willow: Die-Namic plays it there, pinned by its files' hashes ([../../willow.pin.json](../../willow.pin.json)). Its card, with everything it does and refuses: [quiz in willow](https://github.com/willow-memory/Willow/tree/c2b5aa41fd31ab53979ea0d891607ded5f6f3f0a/adapters/stdlib/quiz).

## Playing it

```
python apps/game/games/play.py quiz --table DIR ask
python apps/game/games/play.py quiz --table DIR answer WORD
```

On a box laid by `box/open_table.py`, `--table DIR` plays on its record.

Each move is a row on the record, through the kernel.
