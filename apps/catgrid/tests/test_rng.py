"""catgrid's xorshift32 is bureau's, by test: the named middle between the copy
here and ``apps/bureau/bureau/rng.py``. Pinned outputs are mirrored, not
imported, so the pin can't be true by construction."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

from catgrid.rng import Rng

PINNED = {
    0: [270369, 67634689, 2647435461, 307599695],
    1: [1361127282, 3424972597, 1770954068, 4272703622],
    7: [3860388807, 1365830551, 3479150298, 2887570328],
    2**31: [2148294689, 2365620869, 928901517, 3354237915],
}
BUREAU = Path(__file__).resolve().parents[2] / "bureau"


class TestRng(unittest.TestCase):
    def test_pinned_outputs(self):
        for seed, want in PINNED.items():
            r = Rng(seed)
            self.assertEqual([r.u32() for _ in range(4)], want, seed)

    def test_zero_state_is_never_dead(self):
        seed = (-pow(2654435761, -1, 2**32)) % 2**32  # the seed whose mix is 0
        self.assertNotEqual(Rng(seed).u32(), 0)

    def test_shuffle_is_a_permutation_drawn_from_the_seed(self):
        self.assertEqual(sorted(Rng(3).shuffled(range(9))), list(range(9)))
        self.assertEqual(Rng(3).shuffled(range(9)), Rng(3).shuffled(range(9)))

    @unittest.skipUnless((BUREAU / "bureau" / "rng.py").is_file(), "bureau not beside catgrid")
    def test_same_draws_as_bureau(self):
        sys.path.insert(0, str(BUREAU))
        try:
            from bureau.rng import Rng as BureauRng
        finally:
            sys.path.remove(str(BUREAU))
        for seed in (0, 1, 7, 99, 2**31, 2**32 - 1):
            a, b = Rng(seed), BureauRng(seed)
            self.assertEqual([a.u32() for _ in range(64)], [b.u32() for _ in range(64)])
