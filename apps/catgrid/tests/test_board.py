"""Boards: same seed, same bytes; exactly one answer; the sizes that can't exist
refuse. Pinned digests are mirrored, not recomputed, so a change to how a board
is made can't pass by changing its own pin."""
from __future__ import annotations

import random
import unittest
from unittest import mock

from catgrid import solve
from catgrid.board import Board, NoBoard, address, generate, row_name

PINNED = {
    (1, 1): "4bdfad5396e2b152dd8021f3c354db70ec8a7193837fb16773e8e76928d4f035",
    (7, 4): "ffcacaac17da5bbfe78153945df6c2550b87a255290f117f6a3390c22cfef863",
    (7, 6): "2135cb7a485d596207c0e2e208db74d966ed29cf36a3451f623d1aac9a7ca1fe",
    (42, 8): "1546b572dc827df7d52aeb24e2787e99df78fec4e86af1195c4d51cb05cac024",
}
SIZES = (4, 5, 6, 7)
SEEDS = range(25)


def connected(b: Board, owner: int) -> bool:
    cells = [i for i, o in enumerate(b.regions) if o == owner]
    seen, todo = {cells[0]}, [cells[0]]
    while todo:
        r, c = divmod(todo.pop(), b.n)
        for rr, cc in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
            j = rr * b.n + cc
            if 0 <= rr < b.n and 0 <= cc < b.n and b.regions[j] == owner and j not in seen:
                seen.add(j)
                todo.append(j)
    return len(seen) == len(cells)


class TestAddresses(unittest.TestCase):
    def test_rows_run_on_like_the_cross_table(self):
        self.assertEqual([row_name(i) for i in (0, 25, 26, 27, 51, 52)],
                         ["A", "Z", "AA", "AB", "AZ", "BA"])
        self.assertEqual(address(1, 2), "B3")


class TestTheOneByOne(unittest.TestCase):
    def test_the_base_case(self):
        b = generate(1, 1)
        self.assertEqual(b, Board(n=1, regions=(1,), solution=(0,)))
        self.assertEqual(b.addresses(), ["A1"])


class TestSameSeedSameBoard(unittest.TestCase):
    def test_pinned_digests(self):
        for (seed, n), want in PINNED.items():
            self.assertEqual(generate(seed, n).digest(), want, (seed, n))

    def test_twice_is_identical(self):
        for n in SIZES:
            for seed in range(10):
                self.assertEqual(generate(seed, n).canon(), generate(seed, n).canon())

    def test_seeds_make_different_boards(self):
        self.assertGreater(len({generate(s, 6).digest() for s in SEEDS}), 20)

    def test_the_global_random_is_never_touched(self):
        def refuse(*a, **k):
            raise AssertionError("the global random was used")

        with mock.patch.multiple(random, random=refuse, randrange=refuse,
                                 randint=refuse, choice=refuse, shuffle=refuse):
            self.assertEqual(generate(7, 6).digest(), PINNED[(7, 6)])


class TestEveryBoardHasOneAnswer(unittest.TestCase):
    def test_exactly_one_placement(self):
        for n in SIZES:
            for seed in SEEDS:
                b = generate(seed, n)
                with self.subTest(n=n, seed=seed):
                    self.assertEqual(solve.count(n, b.regions, limit=3), 1)
                    self.assertEqual(next(solve.solutions(n, b.regions)), b.solution)

    def test_regions_are_n_connected_pieces(self):
        for n in SIZES:
            for seed in range(10):
                b = generate(seed, n)
                self.assertEqual(sorted(set(b.regions)), list(range(1, n + 1)))
                for owner in range(1, n + 1):
                    self.assertTrue(connected(b, owner), (n, seed, owner))

    def test_a_board_with_two_answers_is_never_handed_out(self):
        with mock.patch("catgrid.board._repair", return_value=True), \
                mock.patch("catgrid.solve.count", return_value=2):
            with self.assertRaises(NoBoard):
                generate(7, 6, tries=3)


class TestImpossibleSizesRefuse(unittest.TestCase):
    def test_two_and_three_have_no_board(self):
        for n in (2, 3):
            with self.assertRaisesRegex(NoBoard, "can't avoid touching"):
                generate(1, n)
            self.assertEqual(solve.count(n, tuple([1] * n * n), limit=1), 0)

    def test_not_a_size(self):
        for n in (0, -1, True, 2.5, "6"):
            with self.assertRaises(NoBoard):
                generate(1, n)
