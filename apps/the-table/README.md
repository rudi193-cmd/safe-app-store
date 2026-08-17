# The Table — a thin AI Game Master spine

**This is a walking skeleton.** It defines the game protocol, a game-agnostic
GM driver loop, a ledger sink, a registry that names every game, and an
end-to-end proof that EVERY registered game, driven through the loop, ends up
remembered in a tamper-evident ai-game-master ledger — now proven with THREE
adapters behind the same protocol: bureau (single-seat exploration),
crazy_eights (4-seat, hidden info), and scene (single-seat narrative dice
scene), all driven by the identical `run_session`/`LedgerSink`, unmodified,
via `the_table/registry.py`.

> The architecture map — the three-layer spine, the adapter tiers, and how the
> other game apps plug in — is [`docs/the-table-map.html`](docs/the-table-map.html).
> Open it in a browser.

```sh
python3 -m unittest discover -s tests -t .   # from apps/the-table/ — all suites
python3 -m the_table.proof                    # the end-to-end proof (or: python3 the_table/proof.py)
```

## What's here

`the_table/game_session.py` pins the contract every game implements —
`GameSession`, a `Protocol`:

```
reset(seed) -> Observation
current_seat() -> Seat
observe(seat) -> Observation
legal_moves(seat) -> Sequence[Move]
step(seat, move) -> Observation
is_terminal() -> bool
result() -> Result
```

`Move` is opaque and game-defined, but MUST be JSON-serializable — the GM
snapshots every move (and every `Observation.view`) to a ledger, so a value
that doesn't round-trip through `json.dumps`/`json.loads` can't be replayed or
audited later. `Observation` and `Result` are frozen dataclasses, also pinned.

`the_table/bureau_adapter.py` is the first real implementation: `BureauSession`
wraps `bureau.play.Session` (`apps/bureau`) behind `GameSession`. bureau is
single-player (`seats = 1`), so its move vocabulary is small — `("go",
office_id)`, `("hand", office_id)`, `("wait",)`, `("look",)` — each dispatched
to the matching `Session` method. the-table is the *consumer* here: it imports
bureau through a small, local `sys.path` shim and never modifies anything
under `apps/bureau`.

`tests/test_bureau_adapter.py` drives a full bureau playthrough to terminal
across five seeds, checks the result is well-formed, and asserts every
`Observation.view` and every chosen `Move` survives a JSON round-trip.

`the_table/crazy_eights_adapter.py` is the SECOND real implementation, and the
proof that the protocol is game-agnostic: `CrazyEightsSession` (`seats = 4`)
reuses game-lab's real Crazy Eights rule functions — `is_legal`,
`legal_cards`, `make_deck`, `SUITS`, imported from `apps/game-lab/sims/
crazy_eights.py` through a small, local `sys.path` shim, the same pattern
`bureau_adapter.py` uses for `apps/bureau` — for every legality decision;
this module owns none of the rules, only the turn-by-turn loop around them.
It owns its own `random.Random(seed)` (never the global `random` module), so
seeds are deterministic and independent of game-lab. Move vocabulary:
`("play", (rank, suit), suit_call_or_None)`, `("draw",)`, `("pass",)` — a
seat that can't play draws one card at a time (its own auditable ledger row)
rather than game-lab's own self-play draw-until-playable-in-one-ply, so
the-table does not reproduce game-lab's baseline numbers by design — see the
module docstring for why. `observe(seat)` is the real showcase bureau
(single-player) couldn't offer: each seat's view carries its own hand in
full but opponents only as hand-size counts, never as card lists — hidden
information the ledger itself preserves, since `ledger_sink.py` snapshots
exactly what `run_session` passes it.

`tests/test_crazy_eights_adapter.py` drives full games to terminal across six
seeds with a seeded random policy, asserts every `Observation.view` and every
chosen `Move` round-trips through JSON, asserts `legal_moves()` is
side-effect-free (called twice, same result, no state change) both at reset
and mid-game, asserts `observe(0)` never exposes another seat's actual cards,
asserts `current_seat()` visits more than one seat over a game, and drives
`CrazyEightsSession` through the real `run_session` + a real `LedgerSink`
(temp dir), asserting `sink.verify()` is `True` — the second game, through
the identical driver and sink, unchanged.

`the_table/game_engine_adapter.py` is the THIRD real implementation:
`SceneSession` (`seats = 1`) wraps a freeform narrative scene — no board, no
hand of cards, just beats of declared approach → dice roll → narrated
outcome — around `apps/game/engine_v1_7.py`'s `Engine.roll(stat_name)` (2d6 +
stat, bucketed into `ARCHITECT_ROLL` / `SUCCESS_STANDARD` / `CHAOS_BURST`),
imported through the same one-directory `sys.path` shim pattern the other two
adapters use, over `apps/game`. This module reuses only the roll arithmetic;
the prose is its own. It carefully avoids every persistence trap in
`engine_v1_7.py` — it never calls `apply_debility` / `restore_debility` /
`_save_state`, all three of which would write `apps/game/engine_state.json`;
it applies the one-line debility-floor rule itself, in-adapter, against a
fresh `engine.stats` dict it constructs in `reset()`. Determinism is a
documented coupling of `engine_v1_7.py` itself: `Engine.roll` draws from the
*global* `random` module rather than an owned generator, so `reset(seed)`
calls `random.seed(seed)` directly — meaning two scenes must be run to
completion one at a time, never constructed up front and interleaved (see the
determinism note in `the_table/proof.py`). Move vocabulary:
`("act", "Grit"|"Weird"|"Cute"|"Cool")` — the four approaches, offered
unconditionally every beat. `result()` uses a documented SOFT win heuristic
(`winners=[0]` iff successes ≥ chaos bursts) rather than a hard win
condition, the same "no winner" shape `crazy_eights_adapter.py` uses for a
stalled hand.

`tests/test_game_engine_adapter.py` drives full scenes to terminal across
eight seeds, asserts the SOFT winner heuristic, asserts every
`Observation.view` and chosen `Move` round-trips through JSON, asserts
`legal_moves()` is side-effect-free, asserts same-seed-same-sequence
determinism (and that a scene reseeds regardless of prior global `random`
state), and — the two guarantees named in the adapter's own module docstring
— snapshots `apps/game/engine_state.json`'s existence/mtime/bytes before and
after a scene (including one that hits `CHAOS_BURST`) and asserts
byte-identity or continued absence. It also drives `SceneSession` through the
real `run_session` + a real `LedgerSink`, asserting `sink.verify()` is
`True` — the third game, through the identical driver and sink, unchanged.

`the_table/registry.py` is the piece that makes "the GM runs them all"
literal: a small `name -> zero-arg GameSession factory` registry —
`register(name, factory, *, description="")`, `make(name)`, `games()`,
`describe(name)` — with the three built-ins (`"bureau"`, `"crazy_eights"`,
`"scene"`) registered at import time. A factory always returns a FRESH
session (`SceneSession`'s `beats=6` constructor arg is bound in its
registered lambda, so the registry surface itself stays argument-free);
`register()` rejects a duplicate name or a non-callable factory rather than
silently overwriting. This is deliberately small — a dict and four functions,
no plugin discovery, no config files.

`the_table/ledger_sink.py` (`LedgerSink`) writes turns into an
`ai-game-master` campaign box and verifies the resulting hash chain with
`ai-game-master`'s own `bootstrap/verify_ledger.py` — it never touches the
`canon` table and never seals. `tests/test_ledger_sink.py` proves a clean
chain verifies and that a tampered row is refused.

`the_table/gm.py` is the driver that ties the two together: `run_session(game,
policy, seed=..., sink=None, max_turns=1000)` drives any `GameSession` from
`reset` to `result()`, calling `policy(game, seat)` for the seat
`game.current_seat()` reports each turn (never hardcoded to seat 0, so the
same loop drives multi-seat games) and, when given a `sink`, recording
`open_session` / one `snapshot` per turn / `close_session`. Two policies ship:
`first_legal_policy()` (deterministic) and `random_policy(rng)` (seeded).
`sink=None` drives a game with no persistence. `max_turns` is a mandatory cap
— bureau can in principle random-walk past reasonable patience — and hitting
it before `is_terminal()` raises `GMError` (carrying `turns_taken` and
`last_observation`) rather than returning a fabricated `Result`, so a capped
run is never mistaken for a finished one.

`the_table/proof.py` is the end-to-end demonstration, now REGISTRY-DRIVEN
over ALL registered games: it loops over `registry.games()` (today: bureau,
crazy_eights, scene), `make()`s a fresh session per name, wires it to its own
fresh temp `LedgerSink` box, runs it through `run_session` with a seeded
`random_policy`, and asserts per game that it reached a real terminal state
and that `sink.verify()` — `ai-game-master`'s own verifier — accepts the
chain the GM wrote. Each game is driven fully to completion, one at a time,
before the next is even `make()`'d — never constructed up front and
interleaved, because `scene` reseeds the *global* `random` module in its own
`reset()` (a documented coupling of `apps/game/engine_v1_7.py` itself; see
`game_engine_adapter.py`'s module docstring) and interleaving could let that
reseed land between two draws of another game's `random_policy`. Run it with
`python3 -m the_table.proof` or `python3 the_table/proof.py` (both from
`apps/the-table/`); it prints a short section per game (transcript, `Result`,
turn count, chain head, verify result), then a combined line, and exits 0
only if EVERY registered game verifies clean. Adding a fourth game to the
proof is one `registry.register()` call — `proof.py` itself does not change.

`tests/test_gm.py` covers the driver two ways: a tiny in-file stub
`GameSession` (a 2-seat counter) unit-tests the loop's own mechanics — turn
order via `current_seat()`, the terminal stop, the `max_turns` cap path, and
sink call counts — in isolation from bureau; a second test drives the real
`BureauSession` + a real `LedgerSink` through `run_session` and asserts
`sink.verify()` is `True`. The equivalent crazy_eights and scene integration
tests live in `tests/test_crazy_eights_adapter.py` and
`tests/test_game_engine_adapter.py`; `tests/test_registry.py` adds the
registry-level version of the same guarantee — for EVERY name `games()`
returns, `make()` + the real `run_session` + a real `LedgerSink` reaches
terminal and verifies — plus coverage of `games()`'s stable ordering,
`make()`'s freshness (a distinct object every call), and `register()`'s
duplicate-name / non-callable-factory rejection.

## Why a protocol first

A GM that talks to `GameSession` doesn't need to know whether it's running
bureau, a card game, or a board game — it needs `reset`, `observe`,
`legal_moves`, `step`, `is_terminal`, `result`, and a promise that whatever it
snapshots can be replayed. Getting that seam right, with one honest
implementation behind it, was the first slice. `the_table/gm.py` is the
game-agnostic driver on top of it, and `the_table/proof.py` is the evidence
that the whole chain — game, protocol, GM loop, ledger — actually composes: a
game driven through `GameSession` by the GM loop ends up remembered in a
tamper-evident `ai-game-master` ledger, verified by `ai-game-master`'s own
verifier. The second slice, `the_table/crazy_eights_adapter.py`, is the proof
that "protocol" wasn't a euphemism for "bureau's shape": a completely
different game — 4 seats instead of 1, real hidden information, rules reused
from `game-lab` rather than hand-written — plugs into the exact same
`run_session` and `LedgerSink`, neither of which was touched to make it fit.
The third slice, `the_table/game_engine_adapter.py`, plugs in a third shape
again — a freeform narrative scene with no board and no hidden hands, rules
reused from `apps/game`'s dice engine — into the same unmodified loop and
sink. `the_table/registry.py` is what turns three individually-wired proofs
into one: a `name -> factory` map that `proof.py` (and
`tests/test_registry.py`) iterate, so driving "every game the-table knows
about" through the identical `run_session`/`LedgerSink` is a loop over
`registry.games()`, not three copies of the same fifteen lines.

## Baselines

`the_table/baseline.py` plays every registered game at volume through the same
protocol the GM uses and reports the distributions that only show up in bulk.
Measured numbers at N=500 — and the honesty note about a first-seat edge that
looked real at N=300 and washed out at N=500 — live in
[`baselines/baselines-N500.md`](baselines/baselines-N500.md) and
[`baselines/PROVENANCE.md`](baselines/PROVENANCE.md). Reproduce with
`python3 -m the_table.baseline 500`.

## Design & direction

Where the-table is heading, drawn before the code:

- [`docs/the-table-map.html`](docs/the-table-map.html) — the three-layer spine and how the game apps plug in.
- [`docs/homestead-table-vision.md`](docs/homestead-table-vision.md) — why "The Table" belongs under Homestead as module three (the room with no ledger).
- [`docs/storysession-design.md`](docs/storysession-design.md) · [`.html`](docs/storysession-design.html) — the `StorySession` reader that plays a world of atoms it never keeps, plus the Apache-filtered notes on what to adopt from outside (Ink, storylets, clocks, Datasworn).

## Playground tier

`apps/the-table/` is a playground build (contested tier, per
[`stores/README.md`](../../stores/README.md)) — scoped to its own SOIL
collection, default-deny reach, no fleet-store writes. Nothing here is a
standing SAFE app until it is promoted.
