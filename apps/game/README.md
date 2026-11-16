# game: where Die-Namic is built

The store's playground home for **Die-Namic**: the game side of the house,
the box an AI game master keeps a table in. It starts empty on purpose. The
pieces come over one at a time, each as its own step, and when the build
meets the store's promotion bar it is lifted out into its own repo in the
Die-Namic-Systems org.

## What was here: the first engine

[`archive/first-engine/`](archive/first-engine/) is where Die-Namic's game
master started, kept whole and unedited: Jane GM, a Streamlit table run by
Consus, "your AIGM" (Engine Codex v1.5.0.0, `engine_v1_7.py`), with its
2026-04-08 [code review](archive/first-engine/CODE_REVIEW.md), which found it
could not run as it stood.

Its roll is still load-bearing. The 2d6 + stat read in three bands is what
the-table's `SceneSession` rolls through today (the-table's path to it now
points into the archive), and what willow's game-master add-on rebuilt on
the record as strong, weak and miss. Its one closed door is
`Engine.roll(stat, is_creator=True)`: the creator's roll that always
succeeds, which everything since answered with a seal instead. Both are
proposed in `stores/decisions/proposed.json`.

## What's here

- **[the game box](box/)**, brought over from willow's `demo/game-box`: a
  game master's binder that can be asked, the record, prep and
  end-of-night stacks, offers at the table, chapters that carry canon,
  and stories from story-timeline.
- **[the games](games/)**, a folder each, named as willow names its
  add-ons: daily-word, the story (game-master), oracle-text, verse, and the
  play- family: play-backgammon, play-bureau, play-catgrid, play-checkers,
  play-crazy-eights, play-dice, play-dice5e, play-hearts, play-horoscope,
  play-liars-dice, play-life, play-odds, play-quiz, play-tarot. the-table's
  games came out of the table into willow, one add-on each, and are pinned
  back here. Each is a willow add-on and stays
  in willow; its folder says what it is, how to play it, and where it came
  from, and [`games/play.py`](games/play.py) plays any of them on a box's
  record through the pin: `python apps/game/games/play.py play-checkers --table DIR move 11-15`.
- **[willow.pin.json](willow.pin.json)**: the box plays with willow's
  kernel and add-ons where they live, in willow, pinned by commit and by
  each file's SHA-256. The box finds a willow checkout (`WILLOW_ROOT`, or
  one beside safe-app-store) and refuses one whose files differ.

## What came over

The three builds this README said would come next came over whole on
2026-11-16, each in its own folder, moved and not copied; their standalone
catalog entries are archived and point here.

- **[the-table](the-table/)**: the game protocol (`GameSession`) and the
  driver, its adapters over bureau, catgrid and game-lab's rules, the
  one-script sink and the proof. Its games went to willow as add-ons and
  are pinned back here; its three worlds are in the box. Its session
  scripts need willow-bot's one-script and willows-grove checked out beside
  safe-app-store (`the_table/host.py`), and say so when they aren't.
- **[ai-game-master](ai-game-master/)**: the blueprint, its decisions and
  its covenant: the campaign vault's schemas and bootstrap, never a
  campaign. The machine proposes and remembers; a named human seals canon.
- **[game-lab](game-lab/)**: official cited rules, a stdlib self-play
  simulator for each game, and measured N=500 baselines, every number
  traced to a run. Store CI's `game-lab-sims` job is its gate.

## The core, the tests, and the gate

- **[die_namic/](die_namic/)**: Die-Namic's core, import-pure: it imports
  nothing from willow, the store or the network, and is handed what it
  leans on. Its search seam is `die_namic.binder:Binder`: ask the GM's
  binder in your own words, the way willow's UI searches (a page you named
  first, then what your words usually mean, then the ranking), over
  passages and a ranker handed in. It ships the reader; the corpus stays
  with whoever grew it.
- **[box/ask.py](box/ask.py)**: the host side of that seam: the box hands
  the core willow's reading of the binder and willow's pile-rank ranker,
  found through the pin. `python apps/game/box/ask.py "what are the dog's stats"`.
- **[tests/](tests/)**: Die-Namic's own tests, the box's, the games' and
  the core's, run from here with a bare `pytest` (`pytest.ini`), as store CI
  and the promotion gate run them. The builds that came over keep their own
  suites.
- **[promotion.json](promotion.json)**: the attestation the store's gate
  reads, its mechanical pointers filled in. What only a person can state is
  left for them: who verifies it (never its author), its own repo, and that
  the store consumes it.

## The pages

- **[ui/](ui/)**: Die-Namic's front page, a shelf of the games, and a page
  of its own for the ones played in the browser (the Table with its
  chapters, binder and between-sessions side; Hearts, Crazy Eights, Tarot,
  the dice tray, Liar's Dice, Catgrid and Life), laid by `ui/build.py`.
  They play in the browser and keep nothing on the record.
- **[decks/](decks/)**: the card art, fetched by `decks/fetch_decks.py`,
  never committed: public domain or CC0 only.

The pieces willow keeps as add-ons (game-master, play-checkers, play-dice,
play-odds and the rest) stay there, and Die-Namic pins them.
