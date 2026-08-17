# The Table — a thin AI Game Master spine

**This is a walking skeleton.** It defines the game protocol and one working
adapter behind it. No GM loop, no second game, no persistence yet — those are
later bites.

```sh
python3 -m unittest discover -s tests -t .   # from apps/the-table/
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

## Why a protocol first

A GM that talks to `GameSession` doesn't need to know whether it's running
bureau, a card game, or a board game — it needs `reset`, `observe`,
`legal_moves`, `step`, `is_terminal`, `result`, and a promise that whatever it
snapshots can be replayed. Getting that seam right, with one honest
implementation behind it, is the whole of this first slice. The GM loop, a
second game, and a persistence layer (ledger snapshots of each `Observation`/
`Move` pair) compose on top of this contract in later slices — this app is
also shaped to compose with the `ai-game-master` library surfaces
(`apps/ai-game-master`) once that loop lands, but does not depend on them yet.

## Playground tier

`apps/the-table/` is a playground build (contested tier, per
[`stores/README.md`](../../stores/README.md)) — scoped to its own SOIL
collection, default-deny reach, no fleet-store writes. Nothing here is a
standing SAFE app until it is promoted.
