"""``GameSession`` over game-lab's backgammon rules: two seats, one die a step.

A board game with dice: everything on the board is public, and the dice are
the session's own, rolled from its seed. the-table is the CONSUMER: it imports
game-lab's pure backgammon helpers from ``apps/game-lab/sims/baseline_core.py``
through the shared path shim (python-chess is in ``requirements.txt`` only
because that module imports it at the top).

REUSE: the start (``bg_new``), every legal use of one die (``bg_leg``:
entering from the bar first, blocked points, hits, bearing off only from home
and only with an exact or highest-point die) and applying it (``bg_apply``).
Each side counts its own points 1..24 toward home, game-lab's convention.

RESTATED from ``backgammon_once`` (its self-play loop): the opening roll is
re-rolled until the two dice differ, and the higher one moves first with
them; doubles give four dice; 15 borne off wins (with none off for the loser,
a gammon); at 600 turns the lower pip count wins.

STATED SIMPLIFICATION, game-lab's own: the official rule that a player must
use as many dice as possible (and the larger when only one can be used) is
not enforced move by move. game-lab's ``bg_turn`` approximates it by trying
both orders with random moves; here each step uses one die the seat picks,
and the turn ends when every die is used or none of the rest can move.

Move vocabulary (JSON-serializable):
  ("move", die, "enter", point, hit)  ("move", die, "move", from, to, hit)
  ("move", die, "off", from, false)
"""
from __future__ import annotations

import json
import random
from collections.abc import Callable

from .crazy_eights_adapter import _ensure_game_lab_sims_on_path

_ensure_game_lab_sims_on_path()

from baseline_core import bg_apply, bg_leg, bg_new  # noqa: E402  (after the shim)

from .game_session import Observation, Result  # noqa: E402

CHECKERS = 15
TURN_CAP = 600  # backgammon_once's adjudication limit


def _pips(side: dict) -> int:
    return sum(p * c for p, c in side["pts"].items()) + side["bar"] * 25


class BackgammonSession:
    """``GameSession`` adapter over game-lab's backgammon rule functions."""

    seats = 2

    def __init__(self, rng_factory: Callable | None = None) -> None:
        self._rng_factory = rng_factory
        self._sides: list | None = None

    def reset(self, seed: int) -> Observation:
        self._rng = self._rng_factory(seed) if self._rng_factory else random.Random(seed)
        self._sides = [bg_new(), bg_new()]
        while True:
            a, b = self._rng.randint(1, 6), self._rng.randint(1, 6)
            if a != b:
                break
        self._turn = 0 if a > b else 1
        self._dice = [a, b]
        self._turns = 0
        self._winner: int | None = None
        self._done = False
        self._how = ""
        return Observation(seat=self._turn, view=self._view(self._turn), terminal=False, narration=[
            f"New game of backgammon (seed {seed}). Opening roll {a}-{b}: seat {self._turn} moves first."])

    def current_seat(self) -> int:
        self._require()
        return self._turn

    def observe(self, seat: int) -> Observation:
        self._require(seat)
        return Observation(seat=seat, view=self._view(seat), narration=[], terminal=self._done)

    def legal_moves(self, seat: int) -> list:
        self._require(seat)
        if self._done or seat != self._turn:
            return []
        return self._legal(seat)

    def step(self, seat: int, move) -> Observation:
        self._require(seat)
        if self._done:
            raise RuntimeError("step() called on a finished game")
        if seat != self._turn:
            raise ValueError(f"it is seat {self._turn}'s turn, not {seat!r}")
        try:
            plain = json.loads(json.dumps(list(move)))
        except (TypeError, ValueError):
            plain = None
        if plain not in [list(m) for m in self._legal(seat)]:
            raise ValueError(f"{move!r} is not a legal use of a die here")
        die, mv = plain[1], tuple(plain[2:])
        me, opp = self._sides[seat], self._sides[1 - seat]
        me, opp = bg_apply(me, opp, mv)
        self._sides[seat], self._sides[1 - seat] = me, opp
        self._dice.remove(die)
        said = [f"seat {seat} uses a {die}: " + " ".join(str(x) for x in mv)]
        if me["off"] == CHECKERS:
            gammon = self._sides[1 - seat]["off"] == 0
            self._end(seat, "bore off all fifteen" + (" (a gammon)" if gammon else ""))
        elif not self._dice or not self._legal(seat):
            self._next_turn(said)
        if self._done:
            said.append(self._how)
        return Observation(seat=self._turn, view=self._view(self._turn), narration=said,
                           terminal=self._done)

    def is_terminal(self) -> bool:
        self._require()
        return self._done

    def result(self) -> Result:
        self._require()
        scores = {s: float(self._sides[s]["off"]) for s in range(2)}
        if not self._done:
            return Result(winners=[], scores=scores, summary="unfinished")
        return Result(winners=[self._winner], scores=scores,
                      summary=f"seat {self._winner} wins: {self._how}")

    # -- internal ----------------------------------------------------------

    def _legal(self, seat: int) -> list:
        me, opp = self._sides[seat], self._sides[1 - seat]
        out = []
        for die in sorted(set(self._dice)):
            out += [("move", die, *mv) for mv in bg_leg(me, opp, die)]
        return out

    def _next_turn(self, said: list) -> None:
        """Pass the dice; a seat whose roll can't move passes on at once."""
        while True:  # bounded: every pass counts a turn, and TURN_CAP ends the game
            self._turns += 1
            if self._turns >= TURN_CAP:
                a, b = _pips(self._sides[0]), _pips(self._sides[1])
                self._end(0 if a < b else 1, f"adjudicated at {TURN_CAP} turns on pips {a}-{b}")
                return
            self._turn = 1 - self._turn
            d1, d2 = self._rng.randint(1, 6), self._rng.randint(1, 6)
            self._dice = [d1, d2, d1, d2] if d1 == d2 else [d1, d2]
            said.append(f"seat {self._turn} rolls {d1}-{d2}")
            if self._legal(self._turn):
                return
            said.append(f"seat {self._turn} can't move")

    def _end(self, winner, how) -> None:
        self._winner, self._done, self._how = winner, True, how
        self._dice = []

    def _view(self, seat: int) -> dict:
        def side(s):
            d = self._sides[s]
            return {"points": {str(p): c for p, c in sorted(d["pts"].items())},
                    "bar": d["bar"], "off": d["off"], "pips": _pips(d)}
        return {"seat": seat, "me": side(seat), "them": side(1 - seat),
                "dice": sorted(self._dice), "turns": self._turns,
                "current_seat": None if self._done else self._turn}

    def _require(self, seat: int | None = None) -> None:
        if self._sides is None:
            raise RuntimeError("reset(seed) must be called before use")
        if seat is not None and (isinstance(seat, bool) or seat not in (0, 1)):
            raise ValueError(f"backgammon is 2-seat; seat must be 0 or 1, got {seat!r}")
