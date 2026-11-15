# The game box

A game master's binder that can be asked. The box is the GM's pile of
notes, a kernel record over it, the GM's own words list, and the add-ons
that play games on that record. You need a monster's stats: ask the box.
You want what your notes said about a character three sessions ago: ask
the box. Each answer comes from your own pages, with the page and the line.

Whoever holds the key is the game master. A player, a script or a model may
propose, and only the GM's seal makes anything stand. Nothing about the
people at the table is written down. The record keeps characters and seats.

Brought over from willow's `demo/game-box`, where it was built so the
pieces and the code that puts them together were checked together. The
pieces stay in willow, as add-ons, and the box runs on them there, pinned:
[`../willow.pin.json`](../willow.pin.json) names willow's commit and each
file the box runs by its SHA-256, and [`willow_pin.py`](willow_pin.py)
finds a willow checkout (`WILLOW_ROOT`, or one beside safe-app-store) and
refuses one whose files differ.

## What's in the box

| Part | What it is | Read or played by |
|---|---|---|
| [binder/](binder/) | the GM's binder, made up for this demo: [monsters](binder/monsters/) with their stats and weaknesses, [people](binder/people/), four nights of [session notes](binder/sessions/) named by their date, and the [house rules](binder/house-rules.md) | the kernel, every add-on that reads a pile, and [rules](https://github.com/willow-memory/Willow/tree/bdf8d3cb62bf3facfb714b38fd439b6b56fb44dd/adapters/stdlib/rules/) for the house rules |
| [gm-words.txt](gm-words.txt) | the GM's words list: how they ask (`stats`, `damage`, `the prince`) put into the words the binder uses (`grit, hits`, `bite`, `aldric`) | the kernel, on every question |
| [gm-stack.md](gm-stack.md) | the GM's prep sheet: thirteen steps, each with the want it answers | [stack](https://github.com/willow-memory/Willow/tree/bdf8d3cb62bf3facfb714b38fd439b6b56fb44dd/adapters/stdlib/stack/) |
| [gm-end.md](gm-end.md) | the end of the night: the GM's handwritten pages read in, the night compiled, sealed as one, backed up | stack, with [ocr](https://github.com/willow-memory/Willow/tree/bdf8d3cb62bf3facfb714b38fd439b6b56fb44dd/adapters/deps/ocr/) reading the pages |
| [sample-scans/](sample-scans/) | a made-up photo of a fifth night's handwritten page | ocr |
| [ideas.py](ideas.py) | between sessions: story seeds dealt from the box's own words, what was set up and never played, what's still open | [oracle-text](https://github.com/willow-memory/Willow/tree/bdf8d3cb62bf3facfb714b38fd439b6b56fb44dd/adapters/stdlib/oracle-text/), [random-passage](https://github.com/willow-memory/Willow/tree/bdf8d3cb62bf3facfb714b38fd439b6b56fb44dd/adapters/stdlib/random-passage/) |
| [stories/](stories/), [author.py](author.py) | stories written in story-timeline, the writer's workbench in the SAFE App Store, and exported as markdown: [the wasp nest](stories/wasp-nest.md), the cellar's next chapter | author.py makes them worlds; game-master checks and plays them |
| [worlds/](worlds/) | the box's two stories, every name a character: [the lantern fair](worlds/lantern-fair.json), and [the clockwork cellar](worlds/clockwork-cellar.json), a boss room that turns on its dice; and the three the-table authored in the store, [Aetheris](worlds/aetheris.json), [Hasbeen](worlds/hasbeen.json) and [Ironworks](worlds/ironworks.json), as they are | [game-master](https://github.com/willow-memory/Willow/tree/bdf8d3cb62bf3facfb714b38fd439b6b56fb44dd/adapters/stdlib/game-master/), rolling with [play-dice](https://github.com/willow-memory/Willow/tree/bdf8d3cb62bf3facfb714b38fd439b6b56fb44dd/adapters/stdlib/play-dice/) |
| checkers, a logic grid | games played straight onto the record | [play-checkers](https://github.com/willow-memory/Willow/tree/bdf8d3cb62bf3facfb714b38fd439b6b56fb44dd/adapters/stdlib/play-checkers/), [play-catgrid](https://github.com/willow-memory/Willow/tree/bdf8d3cb62bf3facfb714b38fd439b6b56fb44dd/adapters/stdlib/play-catgrid/) |
| [check.md](check.md) | the table's own check: every game played again, every house rule's standing | stack |
| [open_table.py](open_table.py) | the box's code: lays a box, and runs its prep sheet and its check | the kernel and the add-ons above |
| [session.py](session.py) | the GM's bookkeeping, done by code: plays a story as far as it goes without the GM, and says what the table made true | game-master |

## Laying the box

    python apps/game/box/open_table.py open  --table DIR --key FILE
    python apps/game/box/open_table.py prep  --table DIR
    python apps/game/box/open_table.py check --table DIR

`open` lays a fresh box in DIR:

- **`DIR/pile`** is the binder, the folder the record reads.
- **`DIR/words.txt`** is the GM's words list, kept beside the pile, owner-only.
- **`DIR/worlds`** holds the stories. They sit beside the pile, so what the
  record serves is the binder, and what the table made true is sealed.
- **`DIR/record`** is the record: rolls, rulings, seals.

The kernel makes the key at FILE, which must be outside DIR, so the record
never reads it. Then `open` hands each house rule in for the seal and opens
the story. It seals nothing, and ends with seven house rules waiting and the
first scene set (exit 42).

From there it's the kernel and the add-ons' own commands, on `DIR/record`:

- **Ask the binder.** `kernel.py bite --box DIR/record "what are the
  clockwork hound's stats"` serves `monsters/clockwork-hound.md:5`, the stat
  lines themselves, though they never say "stats": the words list carries it.
  "What does the prince want?" finds "Prince Aldric asked for his goats
  back".
- **What the notes said about someone, session by session.**
  `timeline.py --box DIR/record --to FILE "juno"` gives every line about
  Juno, oldest first, dated by each session file's name.
- **The house rules.** Seal each with `kernel.py seal`. Then `rules.py ask
  --box DIR/record Draws` gives the section back, word for word.
- **The story.** `game_master.py act Grit`, `ask` and `settle`, or
  `session.py` to play it through.
- **Checkers and the grid.** `play_checkers.py new`, `move 11-15`, `offer`,
  `settle`; `catgrid.py play`.

## The prep sheet

`prep` runs [gm-stack.md](gm-stack.md) through the stack add-on, and keeps
each run in `DIR/prep/NNN`, so it can be run every week. The thirteen steps,
each with the want it answers:

| # | Want | Step |
|---|---|---|
| 1 | Where do the springs go? (the thread promised for next time) | `timeline "springs"` |
| 2 | What does the prince want? | `timeline "prince"`, Aldric through the words list |
| 3 | When did the Lantern Man come in? | `first-mention "lantern man"` |
| 4 | When did the hound first show up? | `first-mention "clockwork hound"` |
| 5 | Every riddle so far, not the top three | `all "riddle"` |
| 6 | What did I promise for next time? | `all "next time"` |
| 7 | Did we miss a week? | `gaps` |
| 8 | What waits on me? | `digest` |
| 9 | Which house rules have I sealed? | `rules list` |
| 10 | The hound's chances: 2d6 plus its Grit | `odds 2d6+3 --bands 10,7` |
| 11 | The wasps' sting | `odds 1d6` |
| 12 | Did every roll and ruling happen as the record says? | `game-master check` |
| 13 | Is my binder all right? | `box-health` |

**Cards tried and not kept**, because each misreads a GM's notes:

- **nicknames** reads family words beside a name (mum, gran, auntie), not a
  title. "The prince" never reaches it, so the GM's words list carries
  titles by hand.
- **people** counts a name as a person when it speaks or comes, calls,
  asks, tells, pays. A GM's notes say "answered", "found", "pocketed",
  "wanted", so of six characters it found one, Aldric, who "asked".
- **todo** reads TODO, "need to", "remember to" and checkboxes. A GM writes
  "Next time:", so want 6 asks for those words with `all-passages`. That also finds
  the friend Brann was told could come next time.
- **contradictions** reads dates and money, so a hound with six hits on one
  page and eight on another isn't one it can see. No card reads that yet.

## The end of the night

    python apps/game/box/open_table.py end --table DIR

Photograph the night's handwritten pages and put them in `DIR/scans`, named
by the date (`2026-11-21.jpg`). `end` runs [gm-end.md](gm-end.md), each
night kept in `DIR/end/NNN`:

| # | Want | Step |
|---|---|---|
| 1 | Read what I wrote by hand | `ocr mirror` into `DIR/pile/scanned`, where every question finds it |
| 2 | What's new in my binder tonight? | `what-changed`, fingerprints on the record |
| 3 | Where did the springs go tonight? | `timeline`, typed nights and scanned ones together |
| 4 | What did I promise for next time? | `all "next time"` |
| 5 | What's still waiting on me? | `digest` |
| 6 | Tonight, in plain sentences | `history --days 1` |
| 7 | Did every roll and ruling happen as recorded? | `game-master check` |
| 8 | One seal over the whole night | `session-seal`, handed in for the GM |
| 9 | A copy of tonight, checked | `backup` |
| 10 | Where the record ended tonight | `tip-pin` |

Then it prints what the table holds true. The sample page reads back word
for word but one: "(?!)" comes out "(. 1)". OCR guesses, and the binder
cites the line tesseract read, not the page. The page is set in a
handwriting-like font; real handwriting reads worse, and tesseract is made
for print. A check for OCR damage is an idea on willow's list, `ocr-noise`.

## Previously on...

    python apps/game/box/session.py --table DIR recap

For the start of the next session. It has two parts:

- **Read aloud.** Only what the table made true, the sealed canon, so
  nothing the table hasn't heard is said: last time first, then before that,
  then anything sealed tonight so far. A session ends where its session seal
  says, so the end of the night's seal is what makes "last time". An offer
  says whose it was: `[offered by pell]`.
- **For the GM's eyes.** The latest night's notes, typed or scanned, each
  line cited; every promise made for next time; and what the table said no
  to. The binder is the GM's, so none of it is read aloud.

## Between sessions

    python apps/game/box/ideas.py  --table DIR [--seed TEXT]
    python apps/game/box/author.py DIR/stories/wasp-nest.md --to DIR/worlds/wasp-nest.json

**Ideas from the box.** `ideas.py` builds a story-seed grammar out of the
box's own words: the characters and places of the story last played, the
binder's monsters and people, the threads promised for next time, and what
the table made true. The oracle-text add-on deals from it with willow's
seeded stream, so a seed deals the same ideas again:

    - What if Pell finds out where the springs go, and doesn't tell the others?
    - Because the red button is bait, Prince Aldric owes someone at the table a favour.
    - At the gear cellar, Brann comes face to face with the clockwork hound.

It lists what the binder set up and no session has played (the spring
wasps, before the fifth night), every promise still open, and one passage
the GM wrote and may have forgotten, drawn by surprise. Nothing here is
canon or handed in: an idea the GM likes goes into the binder, or a story.

**Stories written in story-timeline.** The writer's workbench in the SAFE
App Store holds the story: a writing project, a timeline, its characters
and places, scene entries, and beat entries after each scene, a beat's
details as the entry's own fields. `export-story` writes the timeline out
as markdown (`promote.py export-story --timeline ID --to FILE`), and
`author.py` makes that a world, checked by game-master. [The wasp nest](stories/wasp-nest.md)
picks the cellar up a week on: the springs lead up into a nest where Old
Vell's lamp may be; the wasps come out only if the climb goes badly; the
table's guest, if one was sealed, has seen Cogwen's machine before; and it
ends on "what is Cogwen building?". It is the next chapter, and it
carries the last one: it opens with Prince Aldric coming to watch only if
the GM sealed him free in the cellar (`when: sealed
clockwork-cellar::room::free is sealed`). A line author.py can't read is refused
with its number, and a world game-master wouldn't play with game-master's
reason.

## The play grows the world

    python apps/game/box/session.py --table DIR export-canon --to canon.md
    python promote.py import-canon canon.md --timeline ID      (in story-timeline)

What the table made true goes back to the writer's timeline, the other half
of the-table's StorySession design. `export-canon` writes every fact the GM
sealed, as markdown, each with its seal (the proposal's hash and row) and
where in play it came from: a story's beat, or "offered by pell as a
guest". A ruling declined stays in the box. In story-timeline,
`import-canon` puts each one on the timeline as a `fact` entry, promoted
with its own `promote_to_timeline` and carrying that provenance; a fact
already there is skipped, so each night's export adds only what's new. The
writer then writes the next chapter knowing it; fact entries are the
writer's chronology, and stay out of the stories the box plays.

The GM seals; the writer promotes. Nothing goes onto the timeline until the
writer runs the import.

## A session, played by code

    python apps/game/box/session.py --table DIR --world clockwork-cellar
    python apps/game/box/session.py --table DIR --world clockwork-cellar offer pell "A guest comes down the stair" --as guest
    python apps/game/box/session.py --table DIR canon

`session.py` is the GM's bookkeeping with no model in it. It rolls each
action beat for the character whose beat it is, leaning into the approach
the beat suggests, and hands each ruling in for the seal. Then it stops
(exit 42) until the GM seals or declines. Run it again and it settles their
answer and plays on. A whole night in the clockwork cellar, the box laid and
three rulings sealed along the way, takes under two seconds.

**What a player brings on the night.** `offer` is a player bringing
something to the table as their character, in their own words: "a guest
comes down the stair: Old Vell from the lantern fair". It is handed in for
the GM's seal, and the story goes on while the GM thinks it over: an offer
sits beside the story's path, so the dice and the beats are the same with it
or without. Once the GM seals or declines it, the next run writes the answer
down before it plays on. A sealed offer is canon that night.

**The story turns on it.** The cellar names one kind of offer it turns on,
`"offers": ["guest"]`. An offer made `--as guest` and sealed before the
story's end gets a beat of its own: Brann asks the guest the table brought
what they came down here for. With no guest sealed, that beat never comes.

`canon` is the table's memory of what it decided. It lists every ruling
sealed on the record whose seal still holds, and every one declined. It
reads only seals, so what it says is what the GM made true; the binder is
what the GM wrote.

## What the tests hold

[test_game_box.py](test_game_box.py) plays it through, with a key made for
the test, the test standing in for the GM:

- **Opening seals nothing.** Seven proposals and no seal. The key is outside
  the box, the words list is owner-only, and the pile is the binder.
- **The binder answers in the GM's words.** A monster's stats, its damage,
  how Cogwen talks, what the prince wants.
- **The prep sheet runs every week.** Two runs, each in its own folder, each
  with its own threads written; the hound's odds and the first mention of
  the Lantern Man on the page. A four-week break is flagged as a gap, and a
  clean run isn't.
- **A whole night.** Seven rules sealed, the story played to its end (one
  ruling sealed, one declined), checkers drawn by the seal, and a grid. The
  table's check then holds every piece: nine seals, all the GM's.
- **Forgeries are caught.** A forged checkers move fails the check. An
  edited row breaks the chain.
- **A session waits for the GM,** and **the dice turn the story**: with a
  copy of the cellar whose Brann always answers the riddle, the prince's
  freeing is put to the GM; with one whose Brann never does, it never is.
  On every real night, canon says the prince is free only if a riddle was
  answered.
- **A guest invented on the night.** Pell's player brings Old Vell down
  the stair mid-session; the story plays on while it waits; once sealed it
  is in canon, marked as Pell's offer. Sealed as a guest, the story gives
  the guest a beat; with none, it doesn't. One declined is canon as a no,
  and only a seated character can offer.
- **Canon is the seals.** A ruling declined shows as a no. Asking the
  record about a scene not played yet serves nothing from the worlds.

## What the box found in its pieces

Each is fixed, and its own tests now hold it.

- **stack** printed "N of M steps flagged (exit 42)" after every run, even
  when nothing was flagged and it exited 0. The line now says the exit it
  makes.
- **stack flagged gaps upside down.** gaps exits 0 when it finds a gap and
  42 when it finds none, as contradictions does, but only contradictions
  was read that way: a clean week was flagged, and a missed one wasn't.
- **session-seal refused the report its card promises.** Its card says
  `output: report`, so a stack asks it for `--json`, and closing a session
  refused `--json` ("check alone"). Closing now prints the report.
- **stack had nowhere fresh for a step to write.** timeline never
  overwrites its file, so a prep sheet could run once. A step can now name
  `{run}`, the folder this run is kept in.
- **game-master's beats ran in one line, whatever the dice did.** A missed
  riddle ("the cage holds") was followed by the ruling "the prince is free".
  A beat can now say `when`: it is played only if an earlier beat came out
  one of its ways.
- **game-master's turns went round the seats whatever the beat said.**
  "Brann answers the riddle" was rolled by Juno. A beat can now say `by`:
  whose beat it is.
- **The box put its worlds in the pile.** Asked "is the red button bait?",
  the record served the world file's own line, sealed or not. The worlds now
  sit beside the pile, and `canon` answers from seals alone.

## Not in the box yet

- **An AI game master.** A model proposing beats, rulings and its own
  offers on loopback, the GM sealing them. `session.py` is the bookkeeping
  it would sit on, and `offer` is the door it would come through.
- **A monster's numbers drifting between pages.** No card reads it yet; it
  is an idea on willow's list, `sheet-drift`.
- **Asking canon in your own words.** The kernel serves a sealed answer to
  the question it was sealed for, so "is the prince free?" finds nothing;
  `canon` lists what's true, but doesn't answer a question about it.
- **Games with hidden hands** (Liar's Dice, Hearts). Anyone at the table can
  read the record, so a hand dealt onto it is not hidden.
