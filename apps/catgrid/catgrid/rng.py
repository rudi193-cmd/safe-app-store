"""xorshift32, ported from ``apps/bureau/bureau/rng.py`` (at 88deb47).

Ported, not imported: catgrid stays self-contained in its lane, so it carries
its own copy, and ``tests/test_rng.py`` is the named middle that keeps the two
copies one generator — it pins the same outputs and, when bureau is beside it,
compares every draw. bureau's reason for specifying the generator holds here
too: ``random.Random`` is Mersenne Twister and reproducible only inside CPython,
and a browser port has to produce the same board from the same seed.

Every shift is masked back to 32 bits so Python's unbounded ints track JS's
``>>> 0``. Do not "simplify" the masking.
"""
from __future__ import annotations

M32 = 0xFFFFFFFF
GOLDEN = 0x9E3779B9


class Rng:
    __slots__ = ("s",)

    def __init__(self, seed: int) -> None:
        s = (seed * 2654435761 + 1) & M32
        self.s = s if s else GOLDEN  # xorshift32 is dead at zero

    def u32(self) -> int:
        x = self.s
        x ^= (x << 13) & M32
        x ^= x >> 17
        x ^= (x << 5) & M32
        self.s = x & M32
        return self.s

    def below(self, n: int) -> int:
        """Uniform-ish in [0, n). Modulo bias is irrelevant at these n."""
        return self.u32() % n

    def pick(self, seq):
        return seq[self.below(len(seq))]

    def shuffled(self, seq) -> list:
        """Fisher-Yates, drawing from this generator only."""
        out = list(seq)
        for i in range(len(out) - 1, 0, -1):
            j = self.below(i + 1)
            out[i], out[j] = out[j], out[i]
        return out
