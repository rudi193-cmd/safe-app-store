# The Table — a thin AI Game Master spine

**This is a walking skeleton.** It defines the game protocol, one working
adapter behind it, a game-agnostic GM driver loop, and an end-to-end proof
that a game driven through the loop is remembered in a tamper-evident
ai-game-master ledger. No second game yet — that's a later bite.

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

`the_table/proof.py` is the end-to-end demonstration: it wires `BureauSession`
+ a `LedgerSink` on a fresh temp box dir, runs `run_session` with a seeded
`random_policy`, and asserts both that the game reached a real terminal state
and that `sink.verify()` — `ai-game-master`'s own verifier — accepts the
chain the GM wrote. Run it with `python3 -m the_table.proof` or
`python3 the_table/proof.py` (both from `apps/the-table/`); it prints a short
transcript, the `Result`, turn count, and chain head, and exits 0 only if the
ledger verifies clean.

`tests/test_gm.py` covers the driver two ways: a tiny in-file stub
`GameSession` (a 2-seat counter) unit-tests the loop's own mechanics — turn
order via `current_seat()`, the terminal stop, the `max_turns` cap path, and
sink call counts — in isolation from bureau; a second test drives the real
`BureauSession` + a real `LedgerSink` through `run_session` and asserts
`sink.verify()` is `True`.

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
verifier. A second game is the next slice; it plugs into the same
`run_session`/`LedgerSink` unchanged.

## Playground tier

`apps/the-table/` is a playground build (contested tier, per
[`stores/README.md`](../../stores/README.md)) — scoped to its own SOIL
collection, default-deny reach, no fleet-store writes. Nothing here is a
standing SAFE app until it is promoted.
