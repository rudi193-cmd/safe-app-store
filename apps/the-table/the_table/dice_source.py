"""dice_source.py -- swap the engine's random source for exactly one roll (R7).

``apps/game/engine_v1_7.py`` is NOT edited. ``Engine.roll`` calls
``random.randint`` through the module-level name ``random``; ``rolled_with``
points that name at an injected source (a ``StreamRandom``) for the length of
one roll and puts back whatever was there in ``finally``, so the global
``random`` module is never seeded, read or advanced, and a roll that raises
still leaves the engine module as it found it.

The swap is process-wide for the length of the ``with`` block: it is not safe
across threads (the docstring says so; one roll is not a long time).
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any


def _engine_module():
    from .game_engine_adapter import _ensure_game_engine_on_path
    _ensure_game_engine_on_path()
    import engine_v1_7
    return engine_v1_7


@contextmanager
def rolled_with(rng: Any, module: Any = None) -> Iterator[Any]:
    mod = module if module is not None else _engine_module()
    previous = mod.random
    mod.random = rng
    try:
        yield rng
    finally:
        mod.random = previous


def roll_record(rng: Any, before: int) -> dict:
    """The ledger fields of one roll: seed id, generator id, counter before and after."""
    m = rng.mark()
    m["counter_before"] = before
    return m
