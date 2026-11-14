# daily-word

A five-letter word game drawn from your own files' words: a new word each day, the same for anyone asking the same folder.

A willow add-on, and it stays in willow: Die-Namic plays it there, pinned by its files' hashes ([../../willow.pin.json](../../willow.pin.json)). Its card, with everything it does and refuses: [daily-word in willow](https://github.com/willow-memory/Willow/tree/9d7c45b0d1ab64e5c07519ec6bbb42489ebb19b1/adapters/stdlib/daily-word).

## Playing it

```
python apps/game/games/play.py daily-word --table DIR today
python apps/game/games/play.py daily-word --table DIR guess WORD
```

On a box laid by `box/open_table.py`, `--table DIR` plays on its record.

Each move is a row on the record, through the kernel.
