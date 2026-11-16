"""dice_source.py -- the table's binding of the one script's dice (flatten F-14).

The swap that points an engine's ``random`` at an injected source for exactly
one roll, the roll record, ``engine_hash`` and ``replay_roll`` all live in the
one script's ``onescript/dice.py``, which takes the engine as an argument.
This module binds the table's engine (``apps/game``'s ``Engine``, found by
``game_engine_adapter``'s path shim) as the default, so the table's callers
read as before. With no one script beside, importing this raises
``host.Unreachable`` and says why (F-16).

``apps/game/engine_v1_7.py`` is still NOT edited; see ``onescript/dice.py``
for the swap's safety rules (one re-entrant lock, LIFO exits, never across a
``yield``).
"""
from __future__ import annotations

from typing import Any

from .host import onescript_module

_dice = onescript_module("dice")
_SWAP_LOCK = _dice._SWAP_LOCK


def _engine_class():
    from .game_engine_adapter import _ensure_game_engine_on_path
    _ensure_game_engine_on_path()
    from engine_v1_7 import Engine
    return Engine


def _or_table(engine: Any) -> Any:
    return engine if engine is not None else _engine_class()


def rolled_with(rng: Any, engine: Any = None):
    """``engine``: an ``Engine`` instance or class (default: apps/game's)."""
    return _dice.rolled_with(rng, _or_table(engine))


def engine_hash(engine: Any = None) -> str:
    """sha256 of the engine module's source bytes (default: apps/game's)."""
    return _dice.engine_hash(_or_table(engine))


def roll(engine: Any, stat: str, rng: Any, stat_value: int) -> tuple:
    """One ``Engine.roll`` under the swap; see ``onescript.dice.roll``."""
    return _dice.roll(engine, stat, rng, stat_value)


def replay_roll(seed, record: dict, sheet: dict | None = None, label: bytes = b"",
                *, unbound_stat_ok: bool = False):
    """Re-verify a recorded roll on the table's engine; see
    ``onescript.dice.replay_roll``."""
    return _dice.replay_roll(seed, record, _engine_class(), sheet, label,
                             unbound_stat_ok=unbound_stat_ok)
