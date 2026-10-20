"""``GameSession`` over game-lab's checkers (English draughts) rules: two seats.

The table's first abstract board game: nothing hidden and nothing random, so
the same moves are the same game. the-table is the CONSUMER: it imports
game-lab's pure checkers helpers from ``apps/game-lab/sims/baseline_core.py``
through the shared path shim and never modifies ``apps/game-lab``. That
module imports python-chess at its top (for its chess baseline), which is why
the-table's ``requirements.txt`` carries ``chess``; its own run is behind
``if __name__ == "__main__":``, so importing it only defines functions.
(``checkers_selfplay.py`` is not used: it plays and writes a file on import.)

REUSE: the start position is ``ck_start``; every legal move, captures
mandatory and multi-jumps whole, promotion ending a jump, is ``ck_legal``;
applying one is ``ck_apply``.

RESTATED from ``checkers_once`` (its self-play loop): a side with no legal
move loses; a side that captures the last enemy piece wins; at 300 moves, or
60 moves without a capture, the game is adjudicated on material (a king
counts 2), even material a draw.

Seats: 0 plays ``a`` (Ada, the top men, moving down the rows, first to move);
1 plays ``h`` (Heimdallr, from the bottom). Kings are ``A`` / ``H``.

Move vocabulary (JSON-serializable):
  ("move", [row, col], [row, col], [[row, col], ...captured], piece_after)
"""
from __future__ import annotations

from collections.abc import Callable

from .crazy_eights_adapter import _ensure_game_lab_sims_on_path

_ensure_game_lab_sims_on_path()

from baseline_core import ck_apply, ck_legal, ck_start  # noqa: E402  (after the shim)

from .game_session import Observation, Result  # noqa: E402

SIDES = ("a", "h")
MOVE_CAP, QUIET_CAP = 300, 60  # checkers_once's adjudication limits


def _wire(mv) -> tuple:
    sq, e, caps, fp = mv
    return ("move", list(sq), list(e), [list(c) for c in sorted(caps)], fp)


def _material(board: dict, side: str) -> int:
    return sum(2 if p.isupper() else 1 for p in board.values() if p.lower() == side)


class CheckersSession:
    """``GameSession`` adapter over game-lab's checkers rule functions."""

    seats = 2

    def __init__(self, rng_factory: Callable | None = None) -> None:
        self._board: dict | None = None  # rng_factory accepted for the registry's shape; nothing is random

    def reset(self, seed: int) -> Observation:
        self._board = ck_start()
        self._turn = 0
        self._moves = 0
        self._quiet = 0
        self._winner: int | None = None
        self._done = False
        self._how = ""
        return Observation(seat=0, view=self._view(0), terminal=False, narration=[
            f"New game of checkers (seed {seed}; nothing in it is random). Ada (seat 0) moves first."])

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
        return [_wire(m) for m in ck_legal(self._board, SIDES[seat])]

    def step(self, seat: int, move) -> Observation:
        self._require(seat)
        if self._done:
            raise RuntimeError("step() called on a finished game")
        if seat != self._turn:
            raise ValueError(f"it is seat {self._turn}'s turn, not {seat!r}")
        side, opp = SIDES[seat], SIDES[1 - seat]
        legal = ck_legal(self._board, side)
        chosen = next((m for m in legal if list(_wire(m)) == _plain(move)), None)
        if chosen is None:
            raise ValueError(f"{move!r} is not a legal move here (captures are mandatory)")
        before = self._board[chosen[0]]
        self._board = ck_apply(self._board, chosen)
        self._moves += 1
        self._quiet = 0 if chosen[2] else self._quiet + 1
        sq, e, caps, fp = chosen
        said = [f"seat {seat} {sq} -> {e}" + (f", takes {len(caps)}" if caps else "")
                + (" and is crowned" if fp != before else "")]
        if not any(p.lower() == opp for p in self._board.values()):
            self._end(seat, "took every piece")
        elif not ck_legal(self._board, opp):
            self._end(seat, f"seat {1 - seat} has no legal move")
        elif self._moves >= MOVE_CAP or self._quiet >= QUIET_CAP:
            mine, theirs = _material(self._board, side), _material(self._board, opp)
            self._end(None if mine == theirs else seat if mine > theirs else 1 - seat,
                      f"adjudicated on material {mine}-{theirs}")
        else:
            self._turn = 1 - seat
        if self._done:
            said.append(self._how)
        return Observation(seat=self._turn, view=self._view(self._turn), narration=said,
                           terminal=self._done)

    def is_terminal(self) -> bool:
        self._require()
        return self._done

    def result(self) -> Result:
        self._require()
        if not self._done:
            return Result(winners=[], scores={}, summary="unfinished")
        scores = {s: float(_material(self._board, SIDES[s])) for s in range(2)}
        if self._winner is None:
            return Result(winners=[], scores=scores, summary=f"a draw: {self._how}")
        return Result(winners=[self._winner], scores=scores,
                      summary=f"seat {self._winner} wins: {self._how}")

    # -- internal ----------------------------------------------------------

    def _end(self, winner, how) -> None:
        self._winner, self._done, self._how = winner, True, how

    def _view(self, seat: int) -> dict:
        rows = ["".join(self._board.get((r, c), "." if (r + c) % 2 else " ") for c in range(8))
                for r in range(8)]
        return {"seat": seat, "side": SIDES[seat], "board": rows, "moves": self._moves,
                "since_capture": self._quiet,
                "material": [_material(self._board, s) for s in SIDES],
                "current_seat": None if self._done else self._turn}

    def _require(self, seat: int | None = None) -> None:
        if self._board is None:
            raise RuntimeError("reset(seed) must be called before use")
        if seat is not None and (isinstance(seat, bool) or seat not in (0, 1)):
            raise ValueError(f"checkers is 2-seat; seat must be 0 or 1, got {seat!r}")


def _plain(move) -> list:
    """A move as plain lists, the way it arrives after a JSON round trip."""
    import json

    try:
        return json.loads(json.dumps(list(move)))
    except (TypeError, ValueError):
        return []
