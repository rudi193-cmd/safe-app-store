"""``GameSession`` over catgrid's ``catgrid.play.Game``.

the-table is the CONSUMER here, as with bureau: it imports catgrid through a
narrow path shim (``apps/catgrid`` on ``sys.path``, once) and touches nothing
under ``apps/catgrid``.

catgrid is single-player (``seats = 1``). Its whole surface is
``catgrid.play.Game`` (read from ``apps/catgrid/catgrid/play.py``): a board
from ``(seed, n)``, ``legal_moves()``, ``step(move) -> narration``, ``state()``
(what a player sees, never the answer) and ``status``. A refused move raises
``catgrid.play.Refused`` (a ``ValueError``) and leaves the game unchanged.

Move vocabulary, JSON-serializable tuples as the contract pins:
  ("cat", cell)  ("x", cell)  ("clear", cell)  -- cells are A1, B3, ...
  ("hint",)  ("trivia",)  ("answer", "A".."D")

Trivia (Jeles) and napkin words (Gerald) are read at ``reset`` from the files
beside the apps unless handed in, and a missing one is the game's own
``unavailable``, said in the view; the board plays the same either way.
"""
from __future__ import annotations

import sys
from pathlib import Path


def _ensure_catgrid_on_path() -> None:
    """Put apps/catgrid on sys.path so ``import catgrid`` works, without
    installing it and without touching anything under apps/catgrid."""
    catgrid_dir = str(Path(__file__).resolve().parents[3] / "apps" / "catgrid")
    if catgrid_dir not in sys.path:
        sys.path.insert(0, catgrid_dir)


_ensure_catgrid_on_path()

from catgrid import eggs, trivia  # noqa: E402  (import after path shim, on purpose)
from catgrid.play import Game  # noqa: E402

from .game_session import Observation, Result

DEFAULT_N = 6


class CatgridSession:
    """``GameSession`` adapter over ``catgrid.play.Game``."""

    seats = 1

    def __init__(self, n: int = DEFAULT_N, k: int = 1, *, bank: list | None = None,
                 words: list | None = None) -> None:
        self.n, self.k = n, k
        self._bank, self._words = bank, words
        self._game: Game | None = None

    # -- GameSession -----------------------------------------------------

    def reset(self, seed: int) -> Observation:
        bank, bank_why = (self._bank, "") if self._bank is not None else trivia.load_jeles()
        words, words_why = (self._words, "") if self._words is not None else eggs.load_napkins()
        self._game = Game.new(seed, self.n, self.k, bank=bank, words=words,
                              bank_why=bank_why or "no trivia bank given",
                              words_why=words_why or "no napkin words given")
        g = self._game
        return Observation(
            seat=0,
            view=g.state(),
            narration=[f"catgrid {self.n}x{self.n}: {self.k} cat(s) in every row, column and "
                       "region; no two touch. Three hearts; one free hint."],
            terminal=g.status != "playing",
        )

    def current_seat(self) -> int:
        return 0

    def observe(self, seat: int) -> Observation:
        self._require(seat)
        g = self._game
        return Observation(seat=0, view=g.state(), narration=[], terminal=g.status != "playing")

    def legal_moves(self, seat: int) -> list:
        self._require(seat)
        return self._game.legal_moves()

    def step(self, seat: int, move) -> Observation:
        self._require(seat)
        g = self._game
        narration = g.step(tuple(move))
        return Observation(seat=0, view=g.state(), narration=list(narration),
                           terminal=g.status != "playing")

    def is_terminal(self) -> bool:
        return self._game is not None and self._game.status != "playing"

    def result(self) -> Result:
        g = self._game
        if g is not None and g.status == "won":
            return Result(winners=[0], scores={0: float(g.hearts)},
                          summary=f"solved with {g.hearts} heart(s) left")
        if g is not None and g.status == "lost":
            return Result(winners=[], scores={0: 0.0}, summary="out of hearts")
        return Result(winners=[], scores={}, summary="unfinished")

    # -- internal ----------------------------------------------------------

    def _require(self, seat: int) -> None:
        if self._game is None:
            raise RuntimeError("reset(seed) must be called before use")
        if seat != 0:
            raise ValueError(f"catgrid is single-player; seat must be 0, got {seat!r}")


class CatgridDuelSession:
    """``GameSession`` over ``catgrid.duel.Duel``: two seats, one seeded board.

    Cats are public; each seat's x marks are its own, so ``observe(seat)`` is
    per seat the way a card game's is (the duel's own D5). Every move passes the
    turn; a seat out of hearts is skipped. ``legal_moves`` is empty for the seat
    not on turn. A refused move raises ``catgrid.play.Refused`` and changes nothing.
    """

    seats = 2

    def __init__(self, n: int = DEFAULT_N, k: int = 1) -> None:
        self.n, self.k = n, k
        self._duel = None

    def reset(self, seed: int) -> Observation:
        from catgrid.duel import Duel

        self._duel = Duel(seed, self.n, self.k)
        return Observation(
            seat=0, view=self._duel.observe(0),
            narration=[f"catgrid for two, {self.n}x{self.n}: cats are shared, marks are "
                       "your own. A right cat scores; a wrong one costs a heart."],
            terminal=False,
        )

    def current_seat(self) -> int:
        self._require(0)
        return self._duel.current()

    def observe(self, seat: int) -> Observation:
        self._require(seat)
        return Observation(seat=seat, view=self._duel.observe(seat), narration=[],
                           terminal=self._duel.over)

    def legal_moves(self, seat: int) -> list:
        self._require(seat)
        return self._duel.legal_moves(seat)

    def step(self, seat: int, move) -> Observation:
        self._require(seat)
        said = self._duel.step(seat, tuple(move))
        nxt = seat if self._duel.over else self._duel.current()
        return Observation(seat=nxt, view=self._duel.observe(nxt), narration=list(said),
                           terminal=self._duel.over)

    def is_terminal(self) -> bool:
        return self._duel is not None and self._duel.over

    def result(self) -> Result:
        d = self._duel
        scores = {s: float(d.score[s]) for s in range(self.seats)}
        if not d.over:
            return Result(winners=[], scores=scores, summary="unfinished")
        w = d.winners()
        summary = ("no one scored" if not w else
                   f"a tie at {d.score[0]}" if len(w) == 2 else
                   f"seat {w[0]} wins {d.score[w[0]]}-{d.score[1 - w[0]]}")
        return Result(winners=w, scores=scores, summary=summary)

    def _require(self, seat: int) -> None:
        if self._duel is None:
            raise RuntimeError("reset(seed) must be called before use")
        if isinstance(seat, bool) or seat not in (0, 1):
            raise ValueError(f"a duel has seats 0 and 1, got {seat!r}")
