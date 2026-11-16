# play-liars-dice

Liar's Dice on the record, every cup dice's own throw: the bids, the wild ones and every call counted as the dice give.

A willow add-on, and it stays in willow: Die-Namic plays it there, pinned by its files' hashes ([../../willow.pin.json](../../willow.pin.json)). Its card, with everything it does and refuses: [play-liars-dice in willow](https://github.com/willow-memory/Willow/tree/dd1e406d66d07fd6397e41880da831e74bbe9696/adapters/stdlib/play-liars-dice).

## Playing it

```
python apps/game/games/play.py play-liars-dice --table DIR new
python apps/game/games/play.py play-liars-dice --table DIR show
python apps/game/games/play.py play-liars-dice --table DIR bid 3 5
python apps/game/games/play.py play-liars-dice --table DIR call
python apps/game/games/play.py play-liars-dice --table DIR check
```

On a box laid by `box/open_table.py`, `--table DIR` plays on its record.

Each cup is dice's own roll row, thrown straight before its round; each bid and call a row, through the kernel. The cups are open for now.

## Where it came from

Liar's Dice, ported from the-table's liar's dice over game-lab's rules and simplifications (apps/the-table, apps/game-lab in this store), checked against game-lab's on 159,920 bids, 100,000 counts and 3,000 whole games.
