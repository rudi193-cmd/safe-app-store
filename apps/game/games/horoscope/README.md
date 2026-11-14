# horoscope

A daily horoscope keyed on your name and the date: same name, same day, same reading, always.

A willow add-on, and it stays in willow: Die-Namic plays it there, pinned by its files' hashes ([../../willow.pin.json](../../willow.pin.json)). Its card, with everything it does and refuses: [horoscope in willow](https://github.com/willow-memory/Willow/tree/9d7c45b0d1ab64e5c07519ec6bbb42489ebb19b1/adapters/stdlib/horoscope).

## Playing it

```
python apps/game/games/play.py horoscope Ana
python apps/game/games/play.py horoscope NAME [--date YYYY-MM-DD] [--coder]
```

It reads no box: it takes its arguments alone.

It writes nothing: no row, no file.
