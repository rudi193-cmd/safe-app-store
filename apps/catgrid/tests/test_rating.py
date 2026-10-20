"""Measured difficulty: the reasoner is sound, blind to the answer, and the
look-ahead rule reaches what the plain rules can't; every number replays."""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest import mock

from catgrid import rating
from catgrid.board import generate
from catgrid.play import HEARTS, Game

SMALL = ((5, 1), (6, 1), (8, 1))


def blind(b):
    return SimpleNamespace(n=b.n, k=b.k, regions=b.regions)


class TestTheReasonerIsSound(unittest.TestCase):
    def test_every_cat_it_places_is_in_the_answer_and_every_mark_is_not(self):
        boards = [generate(s, n, k=k) for n, k in SMALL for s in range(12)]
        boards += [generate(s, 9, k=2) for s in range(3)]
        for b in boards:
            for ahead in (False, True):
                cats, out = rating.deduce(b, ahead=ahead)
                self.assertLessEqual(cats, b.cats(), (b.n, b.k, ahead))
                self.assertFalse(out & b.cats(), (b.n, b.k, ahead))

    def test_it_never_reads_the_answer(self):
        for s in range(6):
            b = generate(s, 6)
            self.assertEqual(rating.deduce(blind(b), ahead=True), rating.deduce(b, ahead=True))

    def test_public_view_carries_no_answer(self):
        g = Game.new(3, 6)
        p = rating.public(g.state())
        self.assertFalse(hasattr(p, "solution"))
        self.assertEqual(rating.deduce(p, ahead=True), rating.deduce(g.board, ahead=True))


class TestThePlainRules(unittest.TestCase):
    # a 4x4 where region 1 is the one cell B1 (index 1); the rest is filler
    B = SimpleNamespace(n=4, k=1, regions=(2, 1, 2, 2, 2, 2, 3, 3, 4, 3, 3, 3, 4, 4, 4, 3))

    def test_a_one_cell_region_gets_its_cat(self):
        cats, _ = rating.deduce(self.B)
        self.assertIn(1, cats)

    def test_a_cat_rules_out_its_neighbours_row_and_column(self):
        _, out = rating.deduce(self.B, cats={1})
        self.assertLessEqual({0, 2, 4, 5, 6}, out)  # touching
        self.assertLessEqual({3, 9, 13}, out)  # its row and column, past the touch

    def test_a_full_line_rules_out_nothing_it_should_not(self):
        _, out = rating.deduce(self.B)
        self.assertNotIn(1, out)


class TestBroken(unittest.TestCase):
    B = SimpleNamespace(n=4, k=1, regions=(1, 1, 2, 2, 1, 1, 2, 2, 3, 3, 4, 4, 3, 3, 4, 4))

    def setUp(self):
        self.lines = rating._lines(self.B)

    def test_touching_cats_are_broken(self):
        # B1 and C2: own rows, columns and regions; only the touch is wrong
        self.assertTrue(rating._broken(self.B, self.lines, {1, 6}, set()))

    def test_a_line_over_its_k_is_broken(self):
        self.assertTrue(rating._broken(self.B, self.lines, {0, 2}, set()))

    def test_a_line_that_cannot_reach_its_k_is_broken(self):
        self.assertTrue(rating._broken(self.B, self.lines, set(), {0, 1, 2, 3}))

    def test_an_open_board_is_not_broken(self):
        self.assertFalse(rating._broken(self.B, self.lines, set(), set()))


class TestTiers(unittest.TestCase):
    def test_look_ahead_reaches_further_than_the_plain_rules(self):
        b = generate(0, 5)
        self.assertLess(rating.plain_share(b), rating.plain_share(b, ahead=True))
        self.assertEqual(rating.tier(b), "ahead")

    def test_the_one_cat_levels_all_fall_to_look_ahead(self):
        for n, k in SMALL:
            for s in range(8):
                self.assertIn(rating.tier(generate(s, n, k=k)), ("plain", "ahead"), (n, s))

    def test_some_two_cat_board_needs_more_than_either(self):
        self.assertIn("beyond", [rating.tier(generate(s, 9, k=2)) for s in range(4)])


class TestPlay(unittest.TestCase):
    def test_careful_play_on_a_reasoned_board_spends_no_heart_and_no_hint(self):
        for s in range(8):
            g = Game(generate(s, 5), s)
            rating._careful(g, rating.Rng(s))
            self.assertEqual((g.status, g.hearts, g.hints["free"]), ("won", HEARTS, 1), s)

    def test_a_random_player_stops_at_the_cap_unresolved(self):
        g = Game(generate(1, 6), 1)
        with mock.patch.object(rating, "RANDOM_CAP", 3):
            rating._random(g, rating.Rng(1))
        self.assertEqual(len(g.moves), 3)

    def test_measure_replays_exactly(self):
        self.assertEqual(rating.measure(5, 1, range(4)), rating.measure(5, 1, range(4)))

    def test_the_report_is_one_row_per_level(self):
        rows = [rating.measure(5, 1, range(2)), rating.measure(6, 1, range(2))]
        text = rating.format_report(rows)
        self.assertEqual(len(text.strip().splitlines()), 2 + len(rows))
        self.assertIn("5x5, 1 cat(s)", text)


if __name__ == "__main__":
    unittest.main()
