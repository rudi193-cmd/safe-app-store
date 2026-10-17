"""stream.py -- the one seeded dice stream for every game (J2, ruling R6).

PROVENANCE: ``Stream`` is copied, algorithm for algorithm, from
``willows-grove/seat/willow/experiments/predictions-2026-10-17/play.py:56-80``
(SHA-256 of ``seed || counter``, first four bytes big-endian; ``below`` by
rejection, no modulo bias; ``shuffle`` a Fisher-Yates from the end). The same
seed gives the same bytes out as ``play.py``'s own ``Stream``; the test
``tests/test_stream.py`` runs both side by side. It is the same on every
Python, which ``random.Random`` is not guaranteed to be.

``StreamRandom`` wraps a ``Stream`` in the ``random.Random``-shaped duck type
that ``dice.roll(expr, random=...)``, ``aetheris5e.dice5e`` and
``Engine.roll`` call: ``randint``, ``choice``, ``shuffle`` (IN PLACE, like
``random.shuffle``; ``Stream.shuffle`` returns a copy and makes the same
swaps), ``random``. It adds ``counter`` (draws consumed so far),
``seed_id`` and ``generator_id`` so a roll can be recorded and re-verified.

``play.py`` stays as it is: it is a frozen experiment record (willows-grove
CLAUDE.md rule 12), so this file is a copy with a test beside it, not an
import target. If the two ever differ, ``tests/test_stream.py`` fails.

C9: an old run keeps the generator it was made with. ``GENERATOR_ID`` names
this one; ``replay`` refuses a record made by any other generator.
"""
from __future__ import annotations

import hashlib
from collections.abc import Sequence
from typing import Any

GENERATOR_ID = "sha256-stream/v1"


class _Legacy:
    """Opt-out marker: ``rng_factory=LEGACY`` keeps the old global-``random``
    path so recorded runs can still be reproduced (C9)."""

    generator_id = "random/global"

    def __repr__(self) -> str:
        return "LEGACY"


LEGACY = _Legacy()
LEGACY_ID = _Legacy.generator_id


def default_factory(seed):
    return StreamRandom.from_seed(seed)


def resolve_factory(rng_factory):
    """None -> the stream (the default); LEGACY -> None (global random);
    else the caller's factory."""
    if rng_factory is None:
        return default_factory
    if rng_factory is LEGACY:
        return None
    return rng_factory


class ReplayRefused(ValueError):
    """A record cannot be replayed as written."""


class GeneratorMismatch(ReplayRefused):
    """A record names a generator other than the one asked to replay it."""


class EngineMismatch(ReplayRefused):
    """A record was rolled by a different engine source than the one loaded."""


class Stream:
    def __init__(self, seed: bytes):
        self.seed, self.n = seed, 0

    @classmethod
    def from_seed(cls, seed: int | bytes | str, label: bytes = b"") -> Stream:
        """int -> big-endian minimal bytes (0 -> b"\\x00"); str -> bytes.fromhex
        (a drand ``randomness``); bytes as given. ``label`` is appended, the way
        play.py appends the question name."""
        return cls(seed_bytes(seed) + label)

    def u32(self) -> int:
        d = hashlib.sha256(self.seed + self.n.to_bytes(8, "big")).digest()
        self.n += 1
        return int.from_bytes(d[:4], "big")

    def below(self, k: int) -> int:
        """Uniform in 0..k-1, by rejection: no modulo bias."""
        if not 1 <= k <= 1 << 32:
            raise ValueError(f"below(k) needs 1 <= k <= 2**32, got {k!r}")
        cap = (1 << 32) - (1 << 32) % k
        while (x := self.u32()) >= cap:
            pass
        return x % k

    def die(self, sides: int) -> int:
        return self.below(sides) + 1

    def shuffle(self, xs: list) -> list:
        xs = list(xs)
        for i in range(len(xs) - 1, 0, -1):
            j = self.below(i + 1)
            xs[i], xs[j] = xs[j], xs[i]
        return xs


def seed_bytes(seed: int | bytes | str) -> bytes:
    if isinstance(seed, bool):
        raise TypeError("seed must be int, bytes or hex str, not bool")
    if isinstance(seed, int):
        if seed < 0:
            raise ValueError("an int seed must be >= 0")
        return seed.to_bytes(max(1, (seed.bit_length() + 7) // 8), "big")
    if isinstance(seed, str):
        return bytes.fromhex(seed)
    if isinstance(seed, (bytes, bytearray)):
        return bytes(seed)
    raise TypeError(f"seed must be int, bytes or hex str, not {type(seed).__name__}")


class StreamRandom:
    """A ``random.Random``-shaped shim over a ``Stream``."""

    generator_id = GENERATOR_ID

    def __init__(self, stream: Stream):
        self.stream = stream

    @classmethod
    def from_seed(cls, seed: int | bytes | str, label: bytes = b"") -> StreamRandom:
        return cls(Stream.from_seed(seed, label))

    @property
    def counter(self) -> int:
        return self.stream.n

    @property
    def seed_id(self) -> str:
        """Short hash of the seed bytes: names the seed without printing it."""
        return hashlib.sha256(self.stream.seed).hexdigest()[:16]

    # -- the random.Random surface the games call ---------------------------
    def randint(self, a: int, b: int) -> int:
        if b < a:
            raise ValueError(f"empty range for randint({a}, {b})")
        return a + self.stream.below(b - a + 1)

    def choice(self, seq: Sequence) -> Any:
        if not len(seq):
            raise IndexError("cannot choose from an empty sequence")
        return seq[self.stream.below(len(seq))]

    def shuffle(self, xs: list) -> None:
        """In place, same swaps as ``Stream.shuffle`` (which returns a copy)."""
        for i in range(len(xs) - 1, 0, -1):
            j = self.stream.below(i + 1)
            xs[i], xs[j] = xs[j], xs[i]

    def random(self) -> float:
        return self.stream.u32() / 2**32

    # -- the record ----------------------------------------------------------
    def mark(self) -> dict:
        """Where the stream stands now: enough, with the seed, to replay."""
        return {"seed_id": self.seed_id, "generator_id": self.generator_id,
                "counter": self.counter}


def seed_label(rng, seed) -> str:
    """What a reset may narrate about its seed: the stream's hashed ``seed_id``
    (a beacon seed fixes every later die, so it is never narrated); a legacy
    or plain ``random.Random`` run keeps the old ``seed=<n>`` text."""
    if isinstance(rng, StreamRandom):
        return f"seed_id={rng.seed_id}"
    return f"seed={seed}"


def replay(seed: int | bytes | str, record: dict, label: bytes = b"") -> StreamRandom:
    """Rebuild the stream a recorded roll came from, positioned at
    ``record["counter_before"]``.

    Refuses (``ReplayRefused``) a record without ``seed_id``, with a counter
    that is not a non-negative int or has ``before > after``; refuses
    (``GeneratorMismatch``) a ``generator_id`` other than this one's and a seed
    whose id differs from the record's (C9, T16)."""
    got = record.get("generator_id")
    if got != GENERATOR_ID:
        raise GeneratorMismatch(
            f"record was made by generator {got!r}; this is {GENERATOR_ID!r} -- not replayed")
    if "seed_id" not in record:
        raise ReplayRefused("record has no seed_id -- not replayed")
    before, after = record.get("counter_before"), record.get("counter")
    for name, v in (("counter_before", before), ("counter", after)):
        if not isinstance(v, int) or isinstance(v, bool) or v < 0:
            raise ReplayRefused(f"record {name} must be a non-negative int, got {v!r}")
    if before > after:
        raise ReplayRefused(f"record counter_before {before} is after counter {after}")
    rng = StreamRandom.from_seed(seed, label)
    if record["seed_id"] != rng.seed_id:
        raise GeneratorMismatch(
            f"seed id {rng.seed_id!r} does not match the record's {record['seed_id']!r}")
    rng.stream.n = before
    return rng
