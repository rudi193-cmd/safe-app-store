"""The thin waist every game implements.

``GameSession`` is the entire contract between a game engine and the GM: reset
to a seed, report whose turn it is, hand out per-seat observations, enumerate
legal moves, advance state one move at a time, and say when it's over. Nothing
in this module knows what a "move" means for any particular game — ``Move`` is
opaque and game-defined, the same way a chess move and a card-game bid are both
just "the thing that happened next." The one constraint that *is* pinned: a
``Move`` MUST be JSON-serializable, because the GM snapshots every move (and
every ``Observation.view``) to a ledger, and a value that can't round-trip
through ``json.dumps``/``json.loads`` can't be replayed or audited later.

This is a walking skeleton. It defines the contract and nothing else — no
matchmaking, no persistence, no policy for choosing moves. Those compose on
top of ``GameSession``, not inside it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Any, Sequence, runtime_checkable

Seat = int
Move = Any  # game-defined; MUST be JSON-serializable


@dataclass(frozen=True)
class Observation:
    seat: "Seat | None"      # whose view (None = public / narration only)
    view: dict               # what this seat sees; JSON-serializable
    narration: list          # list[str], human-readable lines since the last step
    terminal: bool


@dataclass(frozen=True)
class Result:
    winners: list            # list[Seat]; empty = draw / none
    scores: dict             # dict[Seat, float]; {} if not applicable
    summary: str


@runtime_checkable
class GameSession(Protocol):
    seats: int
    def reset(self, seed: int) -> Observation: ...
    def current_seat(self) -> "Seat": ...      # seat to move next; undefined once terminal
    def observe(self, seat: "Seat") -> Observation: ...
    def legal_moves(self, seat: "Seat") -> Sequence[Move]: ...
    def step(self, seat: "Seat", move: Move) -> Observation: ...
    def is_terminal(self) -> bool: ...
    def result(self) -> Result: ...
