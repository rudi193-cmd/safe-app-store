"""registry.py — name -> ``GameSession`` factory, so a driver can run every
registered game the same way instead of naming each one by hand.

This is the piece that makes "the GM runs them all" literal: ``proof.py``
(and anything else that wants to) does not import ``BureauSession``,
``CrazyEightsSession``, and ``SceneSession`` by name and wire each one up
individually -- it asks the registry for ``games()`` and ``make()``s a fresh
session per name, then drives every one of them through the identical
``run_session`` and the same sink. Adding a fourth game later is one
``register()`` call, not a new branch in every driver.

A "factory" here is a zero-arg callable that returns a FRESH ``GameSession``
each time it's called -- never a shared instance. This matters because
``run_session`` mutates the session it's given (``reset``, repeated
``step``), so two runs (e.g. two tests, or two proof games) must never share
one object. ``SceneSession`` takes a constructor arg (``beats``), so its
factory is a small lambda that binds it -- the registry itself stays
argument-free.

Deliberately small: a dict and four functions, nothing more. No plugin
discovery, no config files, no lazy-import machinery -- the six built-in
games are registered at import time, right here, and that is the entire
"catalog."
"""
from __future__ import annotations

from typing import Callable, Dict

from .backgammon_adapter import BackgammonSession
from .bureau_adapter import BureauSession
from .catgrid_adapter import CatgridDuelSession, CatgridSession
from .checkers_adapter import CheckersSession
from .crazy_eights_adapter import CrazyEightsSession
from .game_engine_adapter import SceneSession
from .game_session import GameSession
from .hearts_adapter import HeartsSession
from .liars_dice_adapter import LiarsDiceSession

Factory = Callable[[], GameSession]

_REGISTRY: Dict[str, Factory] = {}
_DESCRIPTIONS: Dict[str, str] = {}


def register(name: str, factory: Factory, *, description: str = "") -> None:
    """Register ``factory`` (a zero-arg callable returning a fresh
    ``GameSession``) under ``name``.

    Raises ``ValueError`` if ``name`` is already registered (no silent
    overwrite -- a duplicate registration is almost certainly a bug, not an
    intentional replace), and ``TypeError`` if ``factory`` is not callable.
    """
    if name in _REGISTRY:
        raise ValueError(f"a game is already registered under {name!r}")
    if not callable(factory):
        raise TypeError(f"factory for {name!r} must be callable, got {factory!r}")
    _REGISTRY[name] = factory
    _DESCRIPTIONS[name] = description


def make(name: str) -> GameSession:
    """Call the factory registered under ``name`` and return the fresh
    ``GameSession`` it produces. Raises ``KeyError`` if ``name`` isn't
    registered."""
    if name not in _REGISTRY:
        raise KeyError(f"no game registered under {name!r}; known games: {games()}")
    return _REGISTRY[name]()


def games() -> list:
    """Registered game names, in stable (sorted) order."""
    return sorted(_REGISTRY)


def describe(name: str) -> str:
    """The one-line description registered alongside ``name``. Raises
    ``KeyError`` if ``name`` isn't registered."""
    if name not in _DESCRIPTIONS:
        raise KeyError(f"no game registered under {name!r}; known games: {games()}")
    return _DESCRIPTIONS[name]


# ── built-in games, registered at import time ───────────────────────────────
#
# Each factory is zero-arg. SceneSession's constructor arg (beats) is bound
# here, in the lambda -- the registry surface itself never takes per-game
# arguments.
register(
    "backgammon",
    BackgammonSession,
    description="2-seat race with dice, one die a step (game-lab's backgammon rules)",
)
register("bureau", BureauSession, description="single-seat exploration (bureau)")
register(
    "catgrid",
    lambda: CatgridSession(n=6),
    description="single-seat seeded logic grid, 6x6: one cat per row, column and region (apps/catgrid)",
)
# 9x9 and 13x13, not the smallest sizes: 8x8 (2 cats) and 12x12 (3 cats) each
# have only 2 rule-keeping arrangements, mirror images, so every board there
# has one of the same two answers (the operator: "move them to 9x9 and 13x13").
register(
    "catgrid_2cat",
    lambda: CatgridSession(n=9, k=2),
    description="catgrid's intermediate level, 9x9: two cats per row, column and region",
)
register(
    "catgrid_3cat",
    lambda: CatgridSession(n=13, k=3),
    description="catgrid's harder intermediate level, 13x13: three cats per row, column and region",
)
register(
    "catgrid_duel",
    lambda: CatgridDuelSession(n=6),
    description="catgrid for two, 6x6: one board, shared cats, private marks, turns in order",
)
register(
    "checkers",
    CheckersSession,
    description="2-seat English draughts, captures mandatory (game-lab's checkers rules)",
)
register(
    "crazy_eights",
    CrazyEightsSession,
    description="4-seat card game with hidden info (game-lab's Crazy Eights rules)",
)
register(
    "hearts",
    HeartsSession,
    description="4-seat trick-taking, one hand with a pass left (game-lab's Hearts rules)",
)
register(
    "liars_dice",
    LiarsDiceSession,
    description="4-seat dice bluffing, hidden cups, ones wild (game-lab's Liar's Dice rules)",
)
register(
    "scene",
    lambda: SceneSession(beats=6),
    description="single-seat narrative dice scene, 6 beats (apps/game's Engine.roll)",
)
