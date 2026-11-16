# play-horoscope

A daily horoscope keyed on your name and the date: same name, same day, same reading, always.

A willow add-on, and it stays in willow: Die-Namic plays it there, pinned by its files' hashes ([../../willow.pin.json](../../willow.pin.json)). Its card, with everything it does and refuses: [play-horoscope in willow](https://github.com/willow-memory/Willow/tree/dd1e406d66d07fd6397e41880da831e74bbe9696/adapters/stdlib/play-horoscope).

## Playing it

```
python apps/game/games/play.py play-horoscope Ana
python apps/game/games/play.py play-horoscope NAME [--date YYYY-MM-DD] [--coder]
```

It reads no box: it takes its arguments alone.

It writes nothing: no row, no file.
