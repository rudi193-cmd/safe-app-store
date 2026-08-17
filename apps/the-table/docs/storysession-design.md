# StorySession — design

> **Status: design, drawn before any code.** The rendered version is
> [`storysession-design.html`](storysession-design.html). Nothing is built from
> this yet — it exists so the shape can be argued with first.

## The one-liner

`StorySession` is the reader that plays a world — and never keeps it. It's a
`GameSession` like the other three adapters, so the-table's driver and ledger run
it unchanged. What makes it a *story* is that it reads a world out of the
flagship Knowledge OS as plain atoms, plays it through the spine, and then
forgets the play. Only two things can outlast a session, and a person authors
both.

## The mechanism

- **Reads the world as atoms** via an injected store (`all()` / `get()`) — and
  never imports story-timeline's code. The world stays in the writer's box
  ("ship the reader, the world stays").
- **Plays** the scenes through the-table's existing driver; the session forgets.
- **Only a person, at the table, can make anything persist:**
  - **propose → SEAL** a fact into the vault (`ai-game-master`; append-only,
    un-retconnable), or leave it `PENDING` the way a sequel hook waits for a human;
  - **promote → a new scene** back into the timeline (`story-timeline`; `put()`
    with a `derived_from: this session` edge — the play grows the world).
- **The players are never written down.** No attendance, no per-person record,
  nothing a child couldn't erase. The room with no ledger, made structural.

## The contract it implements (a GameSession)

The same seven methods the other adapters implement — no new driver, no new ledger:

```
reset(seed)        # open: load the timeline's scenes + entities from the store
current_seat()     # whose turn — a player, or the table
observe(seat)      # what this seat sees — fog of knowledge (the-binder)
legal_moves(seat)  # the approaches this beat: Grit · Weird · Cute · Cool
step(seat, move)   # resolve via Engine.roll (2d6), narrate, advance the scene
is_terminal()      # the timeline's scenes are played out
result()           # how the story went — a summary, not a winner
```

## What it reads

An injected `store` that answers `all()` / `get()` — one filesystem file, no server.

| Collection | From | What the reader pulls |
|---|---|---|
| `…/story-timeline/timeline_entries` | story-timeline | the **scenes** — ordered, `world_date`, `entry_kind` |
| `…/story-timeline/timelines` | story-timeline | which timeline is being played |
| `…/story-timeline/_graph/edges` | story-timeline | the **stakes** — `contradicts_or_tensions_with`, `supports_scene` |
| `…/the-binder/entities` | the-binder | characters & places + how much each seat **recognizes** them |
| `ask-jeles` corpus | ask-jeles | lore on demand — "what does the world know about X?" |

## What can outlast the session — exactly two, both human-gated

1. **Seal a fact into the vault.** A canon-worthy outcome is proposed during play;
   the person at the head of the table seals it. `ai-game-master`.
2. **Promote a scene to the timeline.** A fact the table established becomes a new
   `timeline_entry` in `story-timeline`, written back with provenance.

**Never written: the players.** Only the *world's* canon can persist, and only
when a person seals it.

## The laws it already obeys (each one already sealed)

- **Ship the reader; the world stays in a box.** — the sealed corpus decision.
- **The machine proposes; only a person seals.** — the fleet canon covenant
  ai-game-master enforces.
- **The room with no ledger — a memory that forgets on purpose.** — the Homestead
  Table principle.

## Built vs. new

- **Reused:** `story-timeline` (world), `the-binder` (recognition), `ask-jeles`
  (lore), `apps/game` `Engine.roll` (dice), `the-table` (protocol/driver/ledger),
  `ai-game-master` (vault).
- **New — the only code:** `StorySession` (the reader) + the **propose→seal** seam
  to the vault + the **promote→timeline** seam back into the world.

This closes the store's own gap E3 ("integrations are narrative-only… a story, not
a system") with the first real pipeline across the flagship Knowledge OS — the
store-native way, through shared atoms rather than code that wires apps together.

---

## Adopt from outside — Apache-filtered

A survey of external prior art (OpenSpiel, Ink, Ironsworn/Datasworn, storylets,
Merkle logs, and more). Verdicts are filtered for **Apache-2.0 compatibility**:
permissive code (MIT/BSD/ISC/Apache/CC0) and open specs/ideas are adoptable;
CC-BY *data* is adoptable **with attribution**; GPL/AGPL/CC-BY-NC/CC-BY-SA/
proprietary source is **ideas-only** (mechanics and API shapes aren't
copyrightable). **Verify each `LICENSE` before depending on anything.**

### ADOPT (license-clean)

| Thing | License | Take |
|---|---|---|
| **Ink** (inkle) | MIT | scene-authoring format/runtime. *Caveat: no mature Python runtime — compile `.ink`→JSON with MIT `inklecate` and interpret, or vet a community port.* |
| **Datasworn** oracle **schema** | MIT / system-agnostic | a standard JSON shape for oracle tables + moves |
| Datasworn **content** | CC-BY **and** CC-BY-NC (mixed) | CC-BY tables only, **attributed**; the CC-BY-NC tables must be **excluded** |
| **Clocks** (Blades in the Dark) | mechanic (idea) | segmented progress tracks as a data type, under the tension graph |
| **Storylets / QBN** (Emily Short / Failbetter) | pattern (idea) | scenes gated on world-state preconditions, not a fixed order |
| **Merkle log / RFC 6962** | open spec; Trillian is Apache-2.0 | audit-grade tamper-evidence for sealed canon — *possibly more than a household needs; the existing hash-chain may suffice* |

### LEARN (validate; ideas free even where the source isn't)

- **OpenSpiel** (Apache-2.0) / **PettingZoo** (MIT) / **Gymnasium** (MIT) — our
  protocol *is* their API. Borrow PettingZoo's **AEC** turn model as the formal
  name for `current_seat()`, and Gymnasium's **`terminated` vs `truncated`** split
  for `is_terminal()` (story concluded ≠ table ran out of time).
- **Mythic Chaos Factor** (proprietary) — a single tension dial feeding oracle odds.
- **Foundry VTT** source-vs-derived Document model (proprietary) — validates our
  sealed-canon vs. ephemeral-session split.
- **NarrativeEngine-P** — a negative example (logs everything) that validates our
  forgets-on-purpose stance.

### SKIP

- **ChoiceScript** — non-commercial license blocks reuse (Ink covers it cleanly).
- **Ren'Py / Fungus** — wrong altitude (full VN engines).
- **Ludii** — right idea, wrong stack (academic Java, too heavy).

### Two findings that could change the design — decide before building

1. **Storylets vs. the timeline walk.** Gate scenes on world-atom preconditions
   and play whichever scene the world currently satisfies, rather than walking a
   fixed order. The single most design-significant find.
2. **Ink vs. a bespoke scene DSL.** Ink is MIT and mature; the only friction is a
   Python runtime. A real build-vs-adopt call, not an assumption.

### Validated, not reinvented

Our `reset/observe/legal_moves/step` protocol independently matches OpenSpiel and
PettingZoo — converged-right, twice. "Machine proposes, human seals" is validated
at three depths: TTRPG oracles, Foundry's document model, and 1990s–2000s
drama-management research.
