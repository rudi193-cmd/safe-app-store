"""registry.py — name -> ``GameSession`` factory, so a driver can run every
registered game the same way instead of naming each one by hand.

This is the piece that makes "the GM runs them all" literal: ``proof.py``
(and anything else that wants to) does not import ``BureauSession``,
``CrazyEightsSession``, and ``SceneSession`` by name and wire each one up
individually -- it asks the registry for ``games()`` and ``make()``s a fresh
session per name, then drives every one of them through the identical
``run_session``/``LedgerSink``. Adding a fourth game later is one
``register()`` call, not a new branch in every driver.

A "factory" here is a zero-arg callable that returns a FRESH ``GameSession``
each time it's called -- never a shared instance. This matters because
``run_session`` mutates the session it's given (``reset``, repeated
``step``), so two runs (e.g. two tests, or two proof games) must never share
one object. ``SceneSession`` takes a constructor arg (``beats``), so its
factory is a small lambda that binds it -- the registry itself stays
argument-free.

Deliberately small: a dict and four functions, nothing more. No plugin
discovery, no config files, no lazy-import machinery -- the three built-in
games are registered at import time, right here, and that is the entire
"catalog."
"""
from __future__ import annotations

from typing import Callable, Dict

from .bureau_adapter import BureauSession
from .crazy_eights_adapter import CrazyEightsSession
from .game_engine_adapter import SceneSession
from .game_session import GameSession

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
register("bureau", BureauSession, description="single-seat exploration (bureau)")
register(
    "crazy_eights",
    CrazyEightsSession,
    description="4-seat card game with hidden info (game-lab's Crazy Eights rules)",
)
register(
    "scene",
    lambda: SceneSession(beats=6),
    description="single-seat narrative dice scene, 6 beats (apps/game's Engine.roll)",
)
