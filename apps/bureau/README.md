# bureau — a Bureaucracy homage at UTETY

Answers one question: *is the deadlock graph funny?* Stdlib-only, Python 3.11+,
no runtime dependencies.

```sh
python3 -m pytest tests/ -q                  # 30 tests, 26,188 subtests
python3 -m unittest discover -s tests -t .   # same suite, stdlib runner
python3 -m bureau.play 4                     # play it in a terminal (arg = seed)
python3 -m bureau.verify                     # print the deadlock proof
python3 bureau/web/build.py                  # generate data.json + web/bureau.html
python3 -m bureau.ledger                     # claims awaiting a confidence
```

Built in the `rudi193-cmd/quick-stupids` playground and rebuilt here against
this repo's conventions. That copy is not a dependency and is not synced; this
is the one under CI.

**The differential needs node and skips without it.** The `app-tests` matrix is
Python-only, so the 16,000 comparisons run in a dedicated `bureau-differential`
job. Without it the suite would go green in CI having compared nothing — which
is this repo's own point about coverage being a claim about the harness rather
than about the code.

## The joke, in one sentence

**Every road ends at the same fact, and the building is too polite to say so.**

You attended a lecture you did not sign up for. Records will resolve the
discrepancy on six documents and will happily tell you which six. Four offices
will each hand you something that *looks* like one of them.

- **Jeles** sources concepts, has never been told your name, has no field for
  it. Proves the lecture happened. Not that you were in it.
- **Oakenscroll** attests to threshold crossings. You get an attestation — of
  the room. Entirely true. Does not mention you.
- **Ofshield** notes what passes, *without judgment*, so a note of passing is
  not a finding of attendance. And "you cannot unpass a threshold" closes the
  other road before you find it.
- **The Binder** files everything and deletes nothing. Your discrepancy is filed
  instantly, cross-referenced as a slant, beautifully looked after, and still
  there — resolution would mean deletion, and the Binder does not delete.
- **Pigeon** routes you to all of them, correctly, every time. Pigeon is never
  wrong about a single door and cannot know the graph is closed.
- **Gerald** was there and saw you and has no write authority.
- **Hanz** can read what Gerald writes. Gerald has not written anything.

Every rule is individually reasonable. Nobody is obstructive. Each refusal is
the character being exactly themselves — the personas are Sean's, from
[`apps/utety-chat/data/professors/`](../utety-chat/data/professors/), and each
office's rule is that persona's stated non-negotiable pointed at a records
problem.

## The deadlock is proved, and the false hope is measured

A document has a `kind` (what the docket displays) and a `qual` (the fine print
nobody reads until it matters). `verify.py` searches the graph twice.

**Strict** honours the fine print. **Credulous** matches on kind alone — an
attestation is an attestation — which is not a weaker checker but a model of the
player, and of the Pigeon, both reading the docket rather than the small type.

```
strictly obtainable:    attestation_room, citation, filing_slant, note_passing, slip, ticket
credulously obtainable: ... discrepancy_resolved ...
required, never issued: attestation_presence, filing_resolved, note_judged
false summits:          attestation_room, filing_slant, note_passing
deadlocked: True   looks winnable: True
```

The gap between those verdicts *is* the design, so it is measured rather than
asserted. Both searches are fixpoints; document acquisition is monotone, so each
closure is complete over every strategy, including ones nobody has thought of.

`test_the_gate_can_fail` installs issuers for all three never-issued documents
and asserts the verdict flips. `test_one_mutation_is_not_enough` asserts that
fixing one does not. Without both, "unreachable" would be a mood.

The web docket renders the same gap: until Records refuses you it draws the
checklist by kind and ticks five of six. Then the fine print appears and three
ticks become crosses.

## How you get out

You don't solve it. The escape deliberately lives **outside** the graph the
verifier reasons about, so the proof stays true: no cleverness inside the
building wins.

Surprise is spent, not gained — every visit costs one, and repeat visits cost
the same as new ones. At zero the narrator has stopped being surprised, which
here is a sensory upgrade: the precausal goo becomes visible, and after a
threshold you did not set and cannot predict, Gerald appears.

Three faces, and **blank is one of them**:

| face | meaning | resolves |
| --- | --- | --- |
| word | Hanz reads it | retroactively enrolled |
| blank | Gerald declined, on the record, in napkin form | attendance formally voided |
| grape | the goo is not finished | nothing; the wait resets to a new unknown length |

A blank napkin is a recorded value. No napkin is a missing row. They resolve
differently and the tests enforce it.

The only losing move is to stop going: quit and you are administratively
withdrawn, remaining physically on campus and no longer in the building.

## Lore, and where it is not

Lore is Sean's, from `rudi193-cmd/sean-data-vault` —
`provided-by-sean/stories/{gerald-origin, gerald-and-the-narrator,
oakenscroll-on-the-goo-and-gerald}.md` and
`professional/research/UTETY_EQUATION_INVENTORY.md`. Gerald's write-authority
rule, the napkin, the grape, the goo threshold, the squeakdogs' queueing, Hanz's
orange and the wink are all canon. The discrepancy, the offices and the entire
requirement graph are not.

**This must never share a surface with the campus front.** `rudi193-cmd/utety`
is a COPPA-scoped under-13 product whose second ground rule is *feedback is
about the work, never the learner*. This artifact is a machine for inducing
frustration deliberately. Same lore, separate thing, no route between them.

## The browser port

`bureau/web/engine.js` is a port of the Python, not a rewrite, and
`tests/test_differential.py` runs it under node against the Python across 400
seeds — 16,000 state comparisons, every move. Both engines share an explicit
xorshift32 (`bureau/rng.py`, mirrored in `engine.js`) because `random.Random` is
reproducible only inside CPython, so the same seed gives the same game in a
terminal and in a tab.

Offices, documents, rules and prose are **generated** from `graph.py` by
`build.py`, so prose cannot drift between the engines — that hole is closed.

**What the differential still cannot see:** the page's own rendering layer —
labels, DOM, CSS. Nothing in Python touches those, and a browser found the last
bug there (a class-level `display` beating the `hidden` attribute), not this
suite.

## Feeding the calibration ledger

`bureau/ledger.py` turns structural findings into predictions Oakenscroll's
Office can grade — `python3 -m bureau.ledger` for a dry run.

The distinction it exists to protect: **a false summit is a theorem, not a
prediction.** The fixpoint is arithmetic over the model; filing it at 99% would
log a certainty as a forecast and pull the reliability diagram toward "well
calibrated" on rows that were never in doubt. A calibration ledger fed proofs
stops measuring anything.

So the proofs are not logged. What is logged is the part that can be wrong —
*the model is faithful to the system it describes*. The solver's arithmetic is
sound; the modelling is the risk, and it is where the failure always is. Seven
claims, each with a named falsifier, and **confidence is never auto-assigned**:
`emit()` raises rather than invent the one number the ledger exists to grade.

No import crosses the boundary in either direction — rows are plain dicts in
`state_claim` shape. `CONF_MIN/CONF_MAX` are therefore duplicated and can drift;
`tests/test_ledger.py` checks them against the real source when a checkout is
present and **skips loudly** when it is not.

## Known rough edges

- "Gerald appears" can fire while you are standing in Gerald's office. Left in.
  It is the funniest line in the build.
- Queue tickets are a tax, not a puzzle. They add texture and cost a turn; they
  do not participate in the deadlock.
- The web build carries prose the CLI does not surface as richly, and only the
  web build warms as surprise drops. The terminal version is now the weaker of
  the two presentations.
