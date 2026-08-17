"""gm.py — the game-agnostic GM driver loop.

This is the piece that ties the walking skeleton together: given any
``GameSession`` (bureau today, anything else later) and a ``Policy`` (a
function that picks a legal move), ``run_session`` drives the game from
``reset`` to ``result()``, optionally recording every turn into a
``LedgerSink``.

The loop knows nothing about bureau, or about any particular game's move
vocabulary — it only calls the pinned ``GameSession`` surface
(``game_session.py``) and, when a sink is given, the pinned ``LedgerSink``
surface (``ledger_sink.py``). It is deliberately seat-agnostic: the seat to
move is always read from ``game.current_seat()``, never assumed to be 0, so
the same loop drives a multi-seat game exactly the way it drives bureau's
single seat.

Cap-hit behavior (documented here, not silent): a game that has not reached
``is_terminal()`` after ``max_turns`` steps is a defined, observable outcome,
not a crash and not a quiet success. ``run_session`` raises ``GMError`` in
that case rather than returning a result — a capped-but-unfinished game has
no ``Result`` worth trusting (bureau's own ``result()`` reports "unresolved"
for an unterminated session; see ``bureau_adapter.py``), and a caller that
wants the partial state can still get it from the raised ``GMError``
(``.turns_taken``, ``.last_observation``) rather than having to guess from a
successful-looking return.
"""
from __future__ import annotations

import random
from typing import Callable, Optional

from .game_session import GameSession, Move, Observation, Result, Seat

Policy = Callable[["GameSession", "Seat"], Move]


class GMError(Exception):
    """Raised when the GM loop cannot produce a trustworthy Result.

    Currently the only case: ``max_turns`` was hit before the game reached
    ``is_terminal()``. Carries the partial progress so a caller can inspect
    or log it, rather than the loop silently returning a fabricated Result.
    """

    def __init__(self, message: str, *, turns_taken: int, last_observation: Optional[Observation]):
        super().__init__(message)
        self.turns_taken = turns_taken
        self.last_observation = last_observation


def random_policy(rng: random.Random) -> Policy:
    """A ``Policy`` that picks uniformly among ``game.legal_moves(seat)``."""

    def _policy(game: GameSession, seat: Seat) -> Move:
        legal = game.legal_moves(seat)
        return rng.choice(legal)

    return _policy


def first_legal_policy() -> Policy:
    """A deterministic ``Policy``: always the first legal move."""

    def _policy(game: GameSession, seat: Seat) -> Move:
        legal = game.legal_moves(seat)
        return legal[0]

    return _policy


def run_session(
    game: GameSession,
    policy: Policy,
    *,
    seed: int,
    sink=None,
    max_turns: int = 1000,
    session_id: Optional[str] = None,
) -> Result:
    """Drive ``game`` from ``reset(seed)`` to ``result()`` via ``policy``.

    Game-agnostic: reads ``game.current_seat()`` every turn rather than
    assuming seat 0, so this same loop drives multi-seat games too.

    ``sink`` is optional (``LedgerSink`` or ``None``); when given, records
    ``open_session`` before the loop, one ``snapshot`` per turn, and
    ``close_session`` once the game reaches ``is_terminal()``.

    Raises ``GMError`` if the game has not reached ``is_terminal()`` within
    ``max_turns`` turns -- see the module docstring for why this is a raise,
    not a quiet return.
    """
    if session_id is None:
        session_id = f"run-{seed}"

    obs = game.reset(seed)

    if sink is not None:
        sink.open_session(session_id, {"seed": seed, "seats": game.seats})

    turns = 0
    while not game.is_terminal():
        if turns >= max_turns:
            raise GMError(
                f"max_turns ({max_turns}) reached before the game became terminal "
                f"(session_id={session_id!r}, seed={seed!r})",
                turns_taken=turns,
                last_observation=obs,
            )

        seat = game.current_seat()
        move = policy(game, seat)
        obs = game.step(seat, move)

        if sink is not None:
            note = obs.narration[0] if obs.narration else ""
            sink.snapshot(
                {"turn": turns, "seat": seat, "move": move, "view": obs.view},
                note=note,
            )

        turns += 1

    result = game.result()

    if sink is not None:
        sink.close_session(
            {"winners": result.winners, "scores": result.scores, "summary": result.summary}
        )

    return result
