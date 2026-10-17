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

C9: an old run keeps the generator it was made with. ``GENERATOR_ID`` names
this one; ``replay`` refuses a record made by any other generator.
"""
from __future__ import annotations

import hashlib
from collections.abc import Sequence
from typing import Any

GENERATOR_ID = "sha256-stream/v1"


class GeneratorMismatch(ValueError):
    """A record names a generator other than the one asked to replay it."""


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
        if k <= 0:
            raise ValueError(f"below(k) needs k >= 1, got {k!r}")
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


def rng_fields(rng: Any) -> dict:
    """The row fields a roll carries. Empty for a legacy ``random.Random``,
    so a default-built session's views stay byte-identical to today's."""
    if not isinstance(rng, StreamRandom):
        return {}
    return {"rng": rng.generator_id, "rng_seed_id": rng.seed_id, "rng_counter": rng.counter}


def replay(seed: int | bytes | str, record: dict, label: bytes = b"") -> StreamRandom:
    """Rebuild the stream a recorded roll came from, positioned at the counter
    the roll started at (``record["counter_before"]``, else ``counter``).

    Refuses (``GeneratorMismatch``) a record whose ``generator_id`` is not this
    generator's, and a seed whose id does not match the record's (C9, T16)."""
    got = record.get("generator_id")
    if got != GENERATOR_ID:
        raise GeneratorMismatch(
            f"record was made by generator {got!r}; this is {GENERATOR_ID!r} -- not replayed")
    rng = StreamRandom.from_seed(seed, label)
    if "seed_id" in record and record["seed_id"] != rng.seed_id:
        raise GeneratorMismatch(
            f"seed id {rng.seed_id!r} does not match the record's {record['seed_id']!r}")
    rng.stream.n = record.get("counter_before", record["counter"])
    return rng
