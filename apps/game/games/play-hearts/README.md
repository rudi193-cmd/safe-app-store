# play-hearts

Hearts on the record, hands open and every deal seeded by the record's tip: the passes, the tricks and the moon held to the rules.

A willow add-on, and it stays in willow: Die-Namic plays it there, pinned by its files' hashes ([../../willow.pin.json](../../willow.pin.json)). Its card, with everything it does and refuses: [play-hearts in willow](https://github.com/willow-memory/Willow/tree/dd1e406d66d07fd6397e41880da831e74bbe9696/adapters/stdlib/play-hearts).

## Playing it

```
python apps/game/games/play.py play-hearts --table DIR new
python apps/game/games/play.py play-hearts --table DIR show
python apps/game/games/play.py play-hearts --table DIR pass west 2C QS AH
python apps/game/games/play.py play-hearts --table DIR play 2C
python apps/game/games/play.py play-hearts --table DIR deal
python apps/game/games/play.py play-hearts --table DIR check
```

On a box laid by `box/open_table.py`, `--table DIR` plays on its record.

Each deal, pass and card is a row on the record, through the kernel. The hands are open for now.

## Where it came from

Hearts, ported from the-table's hearts over game-lab's rules (apps/the-table, apps/game-lab in this store), its legal plays checked against game-lab's in 104,000 states and its scoring on 2,000 hands.
