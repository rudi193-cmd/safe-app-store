"""menu.py -- the closed menu: the one way a model picks a move (box-build R12).

SPEC ruling R12 (the act), SPEC-rival §8 R5-the-act, SPEC-documented §13 J7
and its conflicts C14 (a decision beat is never on the menu) and C15
(``set_piece`` is a beat marker, not a menu). Adversarial cases: rival T12 (a
move outside ``legal_moves`` is refused).

What a model may do here is exactly one thing: pick a move **id** from the
numbered menu code hands it, through ratatosk's one-tool contract --
``propose(path=<move id>)`` -- or, in tests, through an injected ``choose``.
Code turns ``legal_moves(seat)`` into ids (``move_ids``: ``act:Grit``), hands
the list over, and accepts the answer only if it is one of those ids
(``move_of``). Everything else is refused and the game goes on by code:

    refused as     when
    off_menu       an id not on the menu (``act:Fly``, ``Grit``, an index, a
                   move tuple, anything but a listed id)
    escalate       the model proposed ``ESCALATE`` (its reason in ``claim``):
                   it goes to the human, who sees the escalate row
    unreachable    ``choose`` raised, timed out, or returned no row

On any refusal the ``fallback`` policy (default ``gm.first_legal_policy()``)
picks the move, so the roll still happens in code (the D0 is
``GameSession.step``), and the refusal is recorded: on the policy's own
``refusals`` list and, when a sink with ``escalate`` is given, as one
``escalate`` verdict row the human can read. A refusal never raises out of
the loop and never picks a move of its own.

A decision beat never reaches ``choose``: ``StorySession.legal_moves`` is
``[]`` there and ``onescript_sink.play_to_decision`` stops before asking a
policy, so the only path past it is the human's seal (R10). This module
raises if it is ever asked for a move with no legal move, rather than guess.

Departure from SPEC-documented §13 (which has the model return an *index*,
and the menu only on ``set_piece`` beats): R12 wins -- the menu is ids
through ``propose(path=...)``, on every action beat; an index is off the
menu. ``set_piece`` (C15) gates only the flowering draft, which lives beside
the narrator in willows-grove (``grove/table_boxes.py``), never a move pick.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from .gm import Policy, first_legal_policy

ESCALATE = "ESCALATE"  # ratatosk/onescript.py: the reserved propose path
OFF_MENU, ESCALATED, UNREACHABLE = "off_menu", "escalate", "unreachable"
TO_HUMAN = "human"


def move_id(move: Any) -> str:
    """The menu id of a move: ``("act", "Grit")`` -> ``act:Grit``. A move
    that is not a tuple/list of strings reads as its ``str``."""
    if isinstance(move, (tuple, list)) and all(isinstance(x, str) for x in move):
        return ":".join(move)
    return str(move)


def move_ids(legal: Sequence[Any]) -> list[str]:
    """The closed menu, in ``legal_moves`` order."""
    return [move_id(m) for m in legal]


def move_of(path: Any, legal: Sequence[Any]) -> Any | None:
    """The legal move whose id is exactly ``path`` (a str), else ``None``.
    An int, a tuple, a stat name alone, or any other shape is not an id."""
    if not isinstance(path, str):
        return None
    for m in legal:
        if move_id(m) == path:
            return m
    return None


def read_pick(got: Any) -> tuple[str | None, str]:
    """``(path, claim)`` from what ``choose`` returned: a str id, or a propose
    row ``{"path": ..., "claim": ...}`` (ratatosk's contract). Anything else is
    ``(None, why)``."""
    if isinstance(got, str):
        return got, ""
    if isinstance(got, dict) and isinstance(got.get("path"), str):
        claim = got.get("claim")
        return got["path"], claim if isinstance(claim, str) else ""
    return None, f"not a move id or a propose row: {type(got).__name__}"


def menu_policy(
    choose: Callable[[list[str]], Any],
    *,
    fallback: Policy | None = None,
    sink: Any = None,
    set_piece_only: bool = False,
) -> Policy:
    """A ``Policy`` whose only model act is ``choose(menu) -> move id``.

    ``choose`` is injected: ratatosk's ``propose(path=<id>)`` turn in the
    seat, a fake in tests. ``fallback`` picks when the pick is refused
    (default: the first legal move). ``sink`` with an ``escalate`` method
    records each refusal as a verdict row. ``set_piece_only=True`` asks the
    model only on a beat whose view says ``set_piece`` (the documented J7
    reading); the default asks on every action beat (R12).

    The returned policy carries ``refusals``: one dict per refused pick
    ``{"reason", "why", "menu", "got", "took", "to"}``, ``to`` = ``"human"``.
    """
    fallback = fallback or first_legal_policy()

    def _policy(game: Any, seat: int) -> Any:
        legal = list(game.legal_moves(seat))
        if not legal:  # C14: a decision beat has no move; it is the human's
            raise RuntimeError(
                "no legal move for this seat: a decision beat is never on the menu"
            )
        if set_piece_only:
            try:
                view = game.observe(seat).view
            except Exception:  # noqa: BLE001 - a game with no view: not a set piece
                view = {}
            if not (isinstance(view, dict) and view.get("set_piece")):
                return fallback(game, seat)
        menu = move_ids(legal)
        try:
            got = choose(list(menu))
        except Exception as e:  # noqa: BLE001 - a model is never trusted to behave
            return _refuse(UNREACHABLE, f"{type(e).__name__}: {e}", menu, None, game, seat)
        path, claim = read_pick(got)
        if path is None:
            return _refuse(UNREACHABLE, claim, menu, got, game, seat)
        if path == ESCALATE:
            return _refuse(ESCALATED, claim or "no reason given", menu, got, game, seat)
        move = move_of(path, legal)
        if move is None:
            return _refuse(OFF_MENU, f"{path!r} is not on the menu", menu, got, game, seat)
        return move

    def _refuse(reason: str, why: str, menu: list[str], got: Any, game: Any, seat: int) -> Any:
        took = fallback(game, seat)
        entry = {
            "reason": reason,
            "why": why,
            "menu": list(menu),
            "got": got if isinstance(got, (str, dict, int, float, list, tuple)) else repr(got),
            "took": move_id(took),
            "to": TO_HUMAN,
            "seat": seat,
        }
        _policy.refusals.append(entry)
        if sink is not None and hasattr(sink, "escalate"):
            sink.escalate(entry)
        return took

    _policy.refusals = []  # type: ignore[attr-defined]
    return _policy
