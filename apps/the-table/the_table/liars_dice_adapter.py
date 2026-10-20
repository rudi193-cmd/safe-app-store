"""``GameSession`` over game-lab's Liar's Dice (Perudo) rules: four seats.

The first dice-bluffing game at the table, and the first where the dice are
hidden: each seat sees its own cup only. the-table is the CONSUMER: it imports
game-lab's pure helpers through the shared path shim and never modifies
``apps/game-lab``; ``apps/game-lab/sims/liars_dice.py`` guards its demo run
behind ``if __name__ == '__main__':``.

REUSE: what counts on a challenge is game-lab's ``count_face`` (ones wild,
except on a bid of ones); which raises are legal is its ``bids_above``; the
table size is its ``NUM_PLAYERS`` / ``DICE_PER_PLAYER``, the cap its
``ROUND_CAP``. game-lab's simplifications hold here too, as its docstring
states them: no Palifico, no exact call, plain (quantity, face) ordering.

RESTATED: ``play_game``'s round loop, so a round can be played one bid at a
time: who loses a die on a challenge (the challenger if the count reaches the
bid, else the bidder) and who opens the next round (the loser, or the next
seat still in). The dice are rolled from this session's own seeded rng, never
game-lab's ``roll``, which draws from the global ``random``.

Turn model (seats = 4):
  * A round: every seat still in rolls its dice under its cup. The opener
    must bid; each seat after either raises, ``("bid", quantity, face)``, or
    calls the last bid, ``("challenge",)``.
  * On a challenge every cup is lifted: the reveal is public, in the
    narration and the view's ``last_reveal``. The loser loses a die; a seat
    with none left is out.
  * Terminal when one seat is left, or at ``ROUND_CAP`` rounds (no winner).
"""
from __future__ import annotations

import random
from collections.abc import Callable

from .crazy_eights_adapter import _ensure_game_lab_sims_on_path

_ensure_game_lab_sims_on_path()

from liars_dice import (  # noqa: E402  (after the shared shim, on purpose)
    DICE_PER_PLAYER,
    NUM_PLAYERS,
    ROUND_CAP,
    bids_above,
    count_face,
)

from .game_session import Observation, Result  # noqa: E402
from .stream import seed_label  # noqa: E402


class LiarsDiceSession:
    """``GameSession`` adapter over game-lab's Liar's Dice rule functions."""

    seats = NUM_PLAYERS

    def __init__(self, rng_factory: Callable | None = None) -> None:
        self._rng_factory = rng_factory
        self._dice: list | None = None

    # -- GameSession -----------------------------------------------------

    def reset(self, seed: int) -> Observation:
        self._rng = self._rng_factory(seed) if self._rng_factory else random.Random(seed)
        self._dice = [DICE_PER_PLAYER] * NUM_PLAYERS
        self._rounds = 0
        self._reveal: dict | None = None
        self._done = False
        self._open_round(0)
        return Observation(seat=self._turn, view=self._view(self._turn), terminal=False,
                           narration=[f"New game of Liar's Dice ({seed_label(self._rng, seed)}): "
                                      f"{NUM_PLAYERS} seats, {DICE_PER_PLAYER} dice each, ones wild."])

    def current_seat(self) -> int:
        self._require()
        return self._turn

    def observe(self, seat: int) -> Observation:
        self._require(seat)
        return Observation(seat=seat, view=self._view(seat), narration=[], terminal=self._done)

    def legal_moves(self, seat: int) -> list:
        """Side-effect-free; empty for a seat not on turn."""
        self._require(seat)
        if self._done or seat != self._turn:
            return []
        raises = [("bid", q, f) for q, f in bids_above(self._bid or (0, 0), self._total())]
        return raises + ([("challenge",)] if self._bid else [])

    def step(self, seat: int, move) -> Observation:
        self._require(seat)
        if self._done:
            raise RuntimeError("step() called on a finished game")
        if seat != self._turn:
            raise ValueError(f"it is seat {self._turn}'s turn, not {seat!r}")
        if isinstance(move, (list, tuple)) and tuple(move) == ("challenge",):
            said = self._challenge(seat)
        elif isinstance(move, (list, tuple)) and len(move) == 3 and move[0] == "bid":
            said = self._raise(seat, move[1], move[2])
        else:
            raise ValueError(f"a move is ('bid', quantity, face) or ('challenge',), not {move!r}")
        return Observation(seat=self._turn, view=self._view(self._turn), narration=said,
                           terminal=self._done)

    def is_terminal(self) -> bool:
        self._require()
        return self._done

    def result(self) -> Result:
        self._require()
        left = self._in()
        if self._done and len(left) == 1:
            return Result(winners=left, scores={s: float(d) for s, d in enumerate(self._dice)},
                          summary=f"seat {left[0]} is the last with dice ({self._rounds} rounds)")
        return Result(winners=[], scores={s: float(d) for s, d in enumerate(self._dice)},
                      summary="round cap reached" if self._done else "unfinished")

    # -- the rules -----------------------------------------------------------

    def _in(self) -> list:
        return [s for s in range(NUM_PLAYERS) if self._dice[s] > 0]

    def _total(self) -> int:
        return sum(self._dice)

    def _open_round(self, opener: int) -> None:
        self._rounds += 1
        self._cups = {s: sorted(self._rng.randint(1, 6) for _ in range(self._dice[s]))
                      for s in self._in()}
        self._bid: tuple | None = None
        self._bidder: int | None = None
        self._history: list = []
        self._turn = opener

    def _next(self, seat: int) -> int:
        for step in range(1, NUM_PLAYERS + 1):
            cand = (seat + step) % NUM_PLAYERS
            if self._dice[cand] > 0:
                return cand
        return seat

    def _raise(self, seat: int, q, f) -> list:
        if isinstance(q, bool) or isinstance(f, bool) or (q, f) not in bids_above(
                self._bid or (0, 0), self._total()):
            raise ValueError(f"({q!r}, {f!r}) is not a raise on {self._bid}")
        self._bid, self._bidder = (q, f), seat
        self._history.append([seat, q, f])
        self._turn = self._next(seat)
        return [f"seat {seat} bids {q} x {f}"]

    def _challenge(self, seat: int) -> list:
        if self._bid is None:
            raise ValueError("there is no bid to challenge; the opener must bid")
        q, f = self._bid
        everything = [d for s in self._in() for d in self._cups[s]]
        actual = count_face(everything, f)
        loser = seat if actual >= q else self._bidder
        self._reveal = {"cups": {str(s): list(c) for s, c in self._cups.items()},
                        "bid": [q, f], "bidder": self._bidder, "challenger": seat,
                        "count": actual, "loser": loser}
        self._dice[loser] -= 1
        said = [f"seat {seat} challenges seat {self._bidder}'s {q} x {f}",
                "cups up: " + "; ".join(f"seat {s} {c}" for s, c in self._cups.items()),
                f"{actual} count as {f}s: seat {loser} loses a die"]
        if len(self._in()) == 1:
            self._done = True
            said.append(f"seat {self._in()[0]} is the last with dice")
        elif self._rounds >= ROUND_CAP:
            self._done = True
            said.append(f"the round cap ({ROUND_CAP}) is reached")
        else:
            self._open_round(loser if self._dice[loser] else self._next(loser))
        return said

    # -- internal ----------------------------------------------------------

    def _view(self, seat: int) -> dict:
        return {
            "seat": seat,
            "my_dice": list(self._cups.get(seat, [])) if not self._done else [],
            "dice_left": list(self._dice),
            "bid": list(self._bid) if self._bid else None,
            "bids_this_round": [list(b) for b in self._history],
            "round": self._rounds,
            "last_reveal": self._reveal,
            "current_seat": None if self._done else self._turn,
        }

    def _require(self, seat: int | None = None) -> None:
        if self._dice is None:
            raise RuntimeError("reset(seed) must be called before use")
        if seat is not None and (isinstance(seat, bool) or seat not in range(NUM_PLAYERS)):
            raise ValueError(f"liar's dice is {NUM_PLAYERS}-seat; got seat {seat!r}")
