# story (game-master)

A tabletop game's rolls and rulings as rows on the record, with the game master's calls sealed.

A willow add-on, and it stays in willow: Die-Namic plays it there, pinned by its files' hashes ([../../willow.pin.json](../../willow.pin.json)). Its card, with everything it does and refuses: [game-master in willow](https://github.com/willow-memory/Willow/tree/bdf8d3cb62bf3facfb714b38fd439b6b56fb44dd/adapters/stdlib/game-master).

## Playing it

```
python apps/game/games/play.py game-master --table DIR open   --world night.json
python apps/game/games/play.py game-master --table DIR status --world night.json
python apps/game/games/play.py game-master --table DIR act Weird --world night.json
python apps/game/games/play.py game-master --table DIR ask    --world night.json
```

On a box laid by `box/open_table.py`, `--table DIR` plays on its record.

Each move is a row on the record, through the kernel.

## Where it came from

The-table's story session (apps/the-table), rebuilt on the record: the box plays its stories through it, and its worlds are the box's (../../box/worlds/).
