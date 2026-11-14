# crazy-eights

Crazy Eights on the record, hands open and the deck seeded by the record's tip: every card, draw and pass held to the rules.

A willow add-on, and it stays in willow: Die-Namic plays it there, pinned by its files' hashes ([../../willow.pin.json](../../willow.pin.json)). Its card, with everything it does and refuses: [crazy-eights in willow](https://github.com/willow-memory/Willow/tree/4b2064071393cef948689ac8fb2badb29faf0a7b/adapters/stdlib/crazy-eights).

## Playing it

```
python apps/game/games/play.py crazy-eights --table DIR new
python apps/game/games/play.py crazy-eights --table DIR show
python apps/game/games/play.py crazy-eights --table DIR play 8H S
python apps/game/games/play.py crazy-eights --table DIR draw
python apps/game/games/play.py crazy-eights --table DIR pass
python apps/game/games/play.py crazy-eights --table DIR check
```

On a box laid by `box/open_table.py`, `--table DIR` plays on its record.

Each deal, card, draw and pass is a row on the record, through the kernel. The hands are open for now.

## Where it came from

Crazy Eights, ported from the-table's crazy eights over game-lab's rules (apps/the-table, apps/game-lab in this store), one card drawn at a time as the-table plays it; its legal cards checked against game-lab's in 159,776 states.
