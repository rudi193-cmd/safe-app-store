"""A deliberately boring PRNG, specified rather than borrowed.

``random.Random`` is Mersenne Twister and reproducible only inside CPython. The
browser port has to produce *the same game* from the same seed or the
differential in ``tests/test_differential.py`` is comparing two different things
and passing anyway. So the generator is xorshift32 with an explicit seed mix,
written twice — here and in ``bureau/web/engine.js`` — in the small number of
operations that mean the same thing in both languages.

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

    def between(self, lo: int, hi: int) -> int:
        """[lo, hi), matching ``random.randrange``'s half-open convention."""
        return lo + self.below(hi - lo)

    def pick(self, seq):
        return seq[self.below(len(seq))]
