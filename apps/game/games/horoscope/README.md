# horoscope

A daily horoscope keyed on your name and the date: same name, same day, same reading, always.

A willow add-on, and it stays in willow: Die-Namic plays it there, pinned by its files' hashes ([../../willow.pin.json](../../willow.pin.json)). Its card, with everything it does and refuses: [horoscope in willow](https://github.com/willow-memory/Willow/tree/1ee630b12fe75cfeafb110aca681acd86cbf0179/adapters/stdlib/horoscope).

## Playing it

```
python apps/game/games/play.py horoscope Ana
python apps/game/games/play.py horoscope NAME [--date YYYY-MM-DD] [--coder]
```

It reads no box: it takes its arguments alone.

It writes nothing: no row, no file.
