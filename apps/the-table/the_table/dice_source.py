"""dice_source.py -- swap the engine's random source for exactly one roll (R7).

``apps/game/engine_v1_7.py`` is NOT edited. ``Engine.roll`` calls
``random.randint`` through the module-level name ``random``; ``rolled_with``
points that name at an injected source (a ``StreamRandom``) for the length of
one roll and puts back what was there in ``finally``, so the global ``random``
module is never seeded, read or advanced by a stream roll.

Safety: the swap is process-wide, so it is held under one module lock
(re-entrant, so a nested ``with`` in the same thread works). Other threads wait
for the roll to finish. On exit the module must still hold OUR source; if not
(a non-LIFO exit, or something else wrote the name) the original value is put
back (at the outermost exit, always what was found before the first swap) and
``RuntimeError`` is raised -- never a silent leak. A legacy
(global ``random``) roll goes through the same door with the real ``random``
module as its source, so a thread cannot see a stream swapped in under it.

The engine is targeted by ``type(engine).roll.__globals__`` -- the namespace
``Engine.roll`` really resolves ``random`` in -- not by an import name.
"""
from __future__ import annotations

import hashlib
import random as _random
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from .stream import EngineMismatch, ReplayRefused, replay

_SWAP_LOCK = threading.RLock()
_ENGINE_HASH: dict = {}
_DEPTH: dict = {}


def _engine_class():
    from .game_engine_adapter import _ensure_game_engine_on_path
    _ensure_game_engine_on_path()
    from engine_v1_7 import Engine
    return Engine


def _globals_of(engine: Any) -> dict:
    cls = engine if isinstance(engine, type) else type(engine)
    return cls.roll.__globals__


@contextmanager
def rolled_with(rng: Any, engine: Any = None) -> Iterator[Any]:
    """``engine``: an ``Engine`` instance or class (default: apps/game's)."""
    g = _globals_of(engine if engine is not None else _engine_class())
    with _SWAP_LOCK:
        st = _DEPTH.setdefault(id(g), [0, None])  # [open swaps, the value before the outermost]
        if st[0] == 0:
            st[1] = g["random"]
        st[0] += 1
        previous = g["random"]
        g["random"] = rng
        try:
            yield rng
        finally:
            st[0] -= 1
            held = g["random"]
            if st[0] == 0:
                g["random"] = st[1]  # outermost exit: always back to what we found
            elif held is rng:
                g["random"] = previous
            if held is not rng:
                raise RuntimeError(
                    "engine random source was changed under rolled_with "
                    "(non-LIFO exit or outside write)")


def engine_hash(engine: Any = None) -> str:
    """sha256 of the engine module's source bytes: names the rules a roll used."""
    g = _globals_of(engine if engine is not None else _engine_class())
    path = g["__file__"]
    if path not in _ENGINE_HASH:
        with open(path, "rb") as f:
            _ENGINE_HASH[path] = hashlib.sha256(f.read()).hexdigest()
    return _ENGINE_HASH[path]


def roll(engine: Any, stat: str, rng: Any, stat_value: int) -> tuple:
    """One ``Engine.roll`` under the swap. ``rng=None`` is the legacy global
    ``random``. Returns ``(result, status, record)``; the record is what a
    ledger row carries (never the raw seed)."""
    source = rng if rng is not None else _random
    before = getattr(source, "counter", None)
    with rolled_with(source, engine):
        result, status = engine.roll(stat)
    rec = {
        "generator_id": getattr(source, "generator_id",
                                "random/global" if rng is None else "random/Random"),
        "result": result, "status": status, "stat_value": stat_value,
        "engine_hash": engine_hash(engine),
    }
    if before is not None:
        rec.update(seed_id=source.seed_id, counter_before=before, counter=source.counter)
    return result, status, rec


def replay_roll(seed, record: dict, label: bytes = b""):
    """Re-verify a recorded roll: the engine source must match the record's
    hash, the stream is rebuilt at ``counter_before``, the roll is redone on a
    fresh engine and must give the recorded result, status and counter."""
    want = record.get("engine_hash")
    have = engine_hash()
    if want != have:
        raise EngineMismatch(f"record was rolled by engine {want!r}; loaded engine is {have!r}")
    rng = replay(seed, record, label)
    for k in ("result", "status", "stat_value"):
        if k not in record:
            raise ReplayRefused(f"record lacks {k!r} -- cannot re-verify the roll")
    Engine = _engine_class()
    eng = Engine()
    eng.stats = {"_s": record["stat_value"]}
    with rolled_with(rng, eng):
        result, status = eng.roll("_s")
    if (result, status, rng.counter) != (record["result"], record["status"], record["counter"]):
        raise ReplayRefused(
            f"replay gave {(result, status, rng.counter)!r}, record says "
            f"{(record['result'], record['status'], record['counter'])!r}")
    return rng
