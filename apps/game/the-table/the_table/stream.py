"""stream.py -- the one seeded stream, imported from the one script (flatten F-14).

``Stream``, ``StreamRandom``, the table's side (``LEGACY``, ``resolve_factory``,
``seed_label``, ``replay`` and its refusals) all live in the one script's
``onescript/stream.py`` (``sha256-stream/v1``). This module is the table's
name for them: every game imports them from here, and here imports them from
the one script beside the-table (``host.onescript_module``; F-16). With no
one script beside, importing this raises ``host.Unreachable`` and says why.

The copy that used to live here (copied, algorithm for algorithm, from the
frozen ``predictions-2026-10-17/play.py``) is gone; ``tests/test_stream.py``
still runs the one script's ``Stream`` side by side with ``play.py``'s.
"""
from __future__ import annotations

from .host import onescript_module

_one = onescript_module("stream")

GENERATOR_ID = _one.GENERATOR_ID
Stream = _one.Stream
StreamRandom = _one.StreamRandom
seed_bytes = _one.seed_bytes
LEGACY = _one.LEGACY
LEGACY_ID = _one.LEGACY_ID
default_factory = _one.default_factory
resolve_factory = _one.resolve_factory
seed_label = _one.seed_label
replay = _one.replay
ReplayRefused = _one.ReplayRefused
GeneratorMismatch = _one.GeneratorMismatch
EngineMismatch = _one.EngineMismatch
_Legacy = type(LEGACY)
