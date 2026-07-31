# band-camp-arcade

Five small, silly, entirely local browser toys for marching band kids. One
HTML file per game, no build step, no accounts, no network calls of any kind.

**Re-landed from the `quick-stupids` playground.** That repository never comes
down local and therefore cannot be a dependency of anything; code worth
keeping is rebuilt here against this repo's conventions rather than imported
from there. Nothing in this app reaches back to it, and the copy there is not
the live one.

```sh
npm install
npm run serve          # http://localhost:8080 — open index.html, no build
npm test               # 18 assertions across five suites, in real Chromium
npm run test:mutations # prove all five gates can fail
```

## The five games

| Game | What it is |
| --- | --- |
| [Tuning Note Purgatory](games/tuning-note-purgatory/) | Hit start, a concert Bb (466.16 Hz) plays forever, hit stop and your time is recorded. Personal best persists. |
| [Pit Crew Simulator](games/pit-crew-simulator/) | Drag front-ensemble instruments onto their marked spots before an 8-count timer runs out. A miss costs a life and retries the same level; a clean clear advances and scores. |
| [Uniform Sweat Tracker](games/uniform-sweat-tracker/) | Log date/event/felt-like-temperature/a 1-10 suffering score/a complaint per game. A season summary picks worst day, best day, average suffering, and a hall-of-fame quote — by score, not by log order. |
| [Sectional Bingo](games/sectional-bingo/) | A shuffled 5x5 card from a 45-line pool of stock sectional disasters, plus a per-user custom pool for section-specific inside jokes. Row/column/diagonal detection triggers a banner and confetti. |
| [GE Score Roast](games/ge-score-roast/) | Enter a fictional score, optional caption and band name, pick a judge persona, get a mad-libs roast back. Satire only — the UI says so, and it is never wired to a real score. |

Everything each game persists is browser `localStorage`, scoped to this
app's origin. See `safe-app-manifest.json`'s `data_streams` for exactly what
each key holds.

## What changed in the rebuild

Re-landing is a rebuild, not a copy — three things changed from the
`quick-stupids` originals:

- **A shared favicon fix.** Each page previously left the browser to request
  `/favicon.ico`, which 404'd and showed up as a console error in every test
  run. `<link rel="icon" href="data:,">` tells the browser not to ask.
- **A nav link tying the five pages into one bundle.** Each game now links
  back to `index.html`, the arcade menu that lists all five — the shape this
  store's `path` = one `app_id` convention expects, and what "wrap them
  together" actually means for five previously-standalone files.
- **Pit Crew Simulator's retry-on-miss behavior.** In the original prototype
  a missed placement still advanced to the next level; that was changed
  (before this re-land) so a miss costs a life and retries the same level
  instead, and the test suite here locks that in.

Nothing about any game's actual mechanics — timers, scoring, drag physics,
bingo detection, roast templates — changed in the rebuild. The rebuild is in
the packaging: the manifest, the catalog entry, and the test harness below,
none of which existed in the playground.

## The gates

`npm test` runs five independent suites in real Chromium — one per game,
18 assertions total, covering exactly what a person clicking through each
game would check: the tuning timer records and persists a best time, a
correctly-dragged instrument clears a pit-crew level and offers the next one,
the sweat tracker's worst/best day summary tracks score rather than log
order, a full bingo row actually triggers BINGO (and clearing a mark clears
the banner), and the roast generator classifies score bands correctly and
actually varies its output on regenerate.

### Proving the gates can fail

A green suite is a claim about the harness, not about the code. `npm run
test:mutations` breaks one specific mechanism per game — the personal-best
save, the level-clear score bump, the worst/best sort, `checkBingo`, and a
score-band boundary — and asserts two things per mutation: the gate it names
goes red, and no undeclared gate does.

All five are caught cleanly. **Building this suite caught a real bug in
itself before this app ever shipped**: the first version of the uniform-
sweat-tracker suite checked "does the worst-day event name appear anywhere in
the summary card's text," which cannot tell a correctly-labeled pair from a
swapped one — both event names are present in the DOM either way. The sort-
reversal mutation exposed it immediately (`NOT CAUGHT`). The fix reads the
DOM structurally instead: which `.summary-item`'s `.value` sits under which
`.label`. The list is in `test/mutations.js`.

### What the suite structurally cannot see

- **Actual audio output.** Tuning Note Purgatory's oscillator and GE Score
  Roast's verdict phrases are asserted to exist and to be triggered; no test
  listens to what comes out of the speakers.
- **Touch input specifically.** Pit Crew Simulator's drag is wired through
  Pointer Events and tested with a synthetic mouse drag; a real touchscreen
  path is unexercised here.
- **Cross-browser behavior.** Everything runs in Chromium only, same
  reasoning as this store's other non-Python app (`jarvis`): the suite is
  about whether the mechanism works at all, not about engine portability.

## Status, and what the green actually covers

`beta` in [`catalog.json`](../../catalog.json). It runs, it is gated, and it
has had one user.

Every number above runs in CI —
[`.github/workflows/band-camp-arcade.yml`](../../.github/workflows/band-camp-arcade.yml)
runs the suite and the mutation pass in real Chromium on every push that
touches `apps/band-camp-arcade/`.

**What that leaves uncovered is worth naming.** The store floor in
[`store-ci.yml`](../../.github/workflows/store-ci.yml) — catalog, vault-clean,
compile, and the drift guards — reads no line of this app's JavaScript, the
same gap `jarvis`'s re-land found and named: those scanners all glob `*.py`,
and this is the second app in the store with none. `tools/vault_leak_lint.py`
reports `UNKNOWN` for this app rather than a false `PASS`, per the fix that
landed with `jarvis`. The floor's actual coverage of this app is the catalog
gate alone; everything else is this app's own workflow.
