"""``GameSession`` over bureau's real ``bureau.play.Session``.

the-table is the CONSUMER here: it imports bureau, never the reverse. bureau
is not installed as a package (no setup.py / pyproject, no console entry), so
the only way to reach it is a path shim — see ``_ensure_bureau_on_path``
below. The shim is intentionally narrow: it adds exactly one directory
(``apps/bureau``, resolved relative to this repo) to ``sys.path``, once, and
touches nothing under ``apps/bureau`` itself.

bureau is single-player (``seats = 1``, ``current_seat()`` is always ``0``).
Its real surface (read in full from ``apps/bureau/bureau/play.py``):

  * ``Session(seed=...)`` — one playthrough.
  * ``.visit(office_id) -> list[str]`` — go to an office; returns narration.
  * ``.hand(office_id) -> list[str]`` — hand over whatever napkin you're
    holding; returns narration.
  * ``.wait() -> list[str]`` — do nothing for a beat; returns narration.
  * ``.look() -> list[str]`` — check what you're holding; returns narration.
  * ``.state() -> dict`` — machine-readable state, no prose (held/surprise/
    dwell/tier/resolution).
  * ``.resolution`` — ``None`` until the discrepancy resolves, then one of
    the two strings bureau's ``hand()`` ever assigns: ``"enrolled"`` or
    ``"voided"`` (``bureau/play.py`` lines 122-131). There is no third,
    negative resolution in the Session class itself — the CLI-only "quit"
    path (``WITHDRAWN``, ``play.py`` main()) never touches ``.resolution``
    and is out of reach of this adapter, which only calls Session methods.

Move vocabulary (JSON-serializable tuples, per the pinned contract):
  ("go", office_id)   -- Session.visit(office_id)
  ("hand", office_id) -- Session.hand(office_id)
  ("wait",)           -- Session.wait()
  ("look",)            -- Session.look()
"""
from __future__ import annotations

import sys
from pathlib import Path


def _ensure_bureau_on_path() -> None:
    """Put apps/bureau on sys.path so ``from bureau.play import Session``
    works, without installing bureau as a package and without touching
    anything under apps/bureau itself.

    Resolved relative to this file: apps/the-table/the_table/bureau_adapter.py
    -> repo root is three parents up -> apps/bureau is the sibling app.
    """
    repo_root = Path(__file__).resolve().parents[3]
    bureau_dir = repo_root / "apps" / "bureau"
    bureau_str = str(bureau_dir)
    if bureau_str not in sys.path:
        sys.path.insert(0, bureau_str)


_ensure_bureau_on_path()

from bureau.play import Session  # noqa: E402  (import after path shim, on purpose)
from bureau import graph as G  # noqa: E402

from .game_session import Observation, Result

# bureau's offices are always visitable — the game itself never gates which
# office you may walk into, only what happens once you're there (graph.py's
# OFFICE_ORDER is the fixed, complete list printed in play.OPENING).
_GO_TARGETS = tuple(G.OFFICE_ORDER)

# Session.hand(office_id) only does anything for these two ids (play.py
# lines 122-131) -- every other office_id just returns a generic "nothing to
# hand over" line. Offering hand() for the other seven offices would not be
# rejected by bureau, but it also would never do anything, so it is left out
# of the legal set: "keep the legal set honest" means honest about what
# *matters*, not just about what bureau declines to error on.
_HAND_TARGETS = ("hanz", "records")


class BureauSession:
    """``GameSession`` adapter over ``bureau.play.Session``."""

    seats = 1

    def __init__(self) -> None:
        self._session: Session | None = None

    # -- GameSession -----------------------------------------------------

    def reset(self, seed: int) -> Observation:
        self._session = Session(seed=seed)
        from bureau.play import OPENING

        narration = [line for line in OPENING.rstrip("\n").split("\n")]
        narration += self._session.look()
        return Observation(
            seat=0,
            view=self._session.state(),
            narration=narration,
            terminal=self._session.resolution is not None,
        )

    def current_seat(self) -> int:
        return 0

    def observe(self, seat: int) -> Observation:
        self._require(seat)
        s = self._session
        return Observation(
            seat=0,
            view=s.state(),
            narration=[],
            terminal=s.resolution is not None,
        )

    def legal_moves(self, seat: int) -> list:
        self._require(seat)
        moves: list = [("go", office_id) for office_id in _GO_TARGETS]
        moves += [("hand", office_id) for office_id in _HAND_TARGETS]
        moves.append(("wait",))
        moves.append(("look",))
        return moves

    def step(self, seat: int, move) -> Observation:
        self._require(seat)
        s = self._session
        verb, *args = move
        if verb == "go":
            narration = s.visit(args[0])
        elif verb == "hand":
            narration = s.hand(args[0])
        elif verb == "wait":
            narration = s.wait()
        elif verb == "look":
            narration = s.look()
        else:
            raise ValueError(f"unknown move verb {verb!r} in {move!r}")
        return Observation(
            seat=0,
            view=s.state(),
            narration=list(narration),
            terminal=s.resolution is not None,
        )

    def is_terminal(self) -> bool:
        return self._session is not None and self._session.resolution is not None

    def result(self) -> Result:
        s = self._session
        resolution = s.resolution if s is not None else None
        # bureau's Session only ever assigns "enrolled" or "voided" (both are
        # completions of the discrepancy, not a loss condition -- see module
        # docstring). Either one is treated as a win for the lone seat; no
        # resolution (game not yet terminal, or never reached) is a draw/none.
        if resolution in ("enrolled", "voided"):
            return Result(
                winners=[0],
                scores={0: 1.0},
                summary=f"Discrepancy 4471-b: {resolution}",
            )
        return Result(winners=[], scores={}, summary="unresolved")

    # -- internal ----------------------------------------------------------

    def _require(self, seat: int) -> None:
        if self._session is None:
            raise RuntimeError("reset(seed) must be called before use")
        if seat != 0:
            raise ValueError(f"bureau is single-player; seat must be 0, got {seat!r}")
