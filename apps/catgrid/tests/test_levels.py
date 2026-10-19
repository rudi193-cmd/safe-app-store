"""Intermediate levels: 2 and 3 cats per row, column and region (the operator:
"2 and 3 cats per color ... intermediate levels"). The same rules, the same
determinism, the same one answer; each by the board or move it forbids."""
from __future__ import annotations

import unittest

from catgrid import solve, soil
from catgrid.board import LARGEST, SMALLEST, NoBoard, address, generate
from catgrid.play import HEARTS, Game, Refused

PINNED = {  # mirrored, not recomputed
    (7, 8, 2): "c12004bd9300a32f84c2e4e33edf7aa6011435b95db329680e30860c61147578",
    (3, 10, 2): "bb033d378285078e414b061b0449b78c49e8c2b49bccac1b7ad63caccd45723b",
    (7, 12, 3): "300557be5525b855ec8ca257d4860ff186e63f42bddee6c5eaa285951f22089c",
}
LEVELS = ((8, 2), (9, 2), (12, 3))


def cells(b):
    return [(r, c) for r, cs in enumerate(b.solution) for c in cs]


class TestTheSizesThatCanExist(unittest.TestCase):
    def test_too_small_refuses_and_truly_has_no_placement(self):
        for k, n in ((2, SMALLEST[2] - 1), (3, SMALLEST[3] - 1)):
            with self.assertRaisesRegex(NoBoard, "can't avoid touching"):
                generate(1, n, k=k)
            self.assertIsNone(solve.placements_k(n, k, lambda r, rows: rows))

    def test_the_smallest_has_one(self):
        for k, n in SMALLEST.items():
            self.assertIsNotNone(solve.placements_k(n, k, lambda r, rows: rows))

    def test_out_of_range(self):
        for n, k in ((LARGEST[2] + 1, 2), (LARGEST[3] + 1, 3), (16, 4), (8, 0), (8, True)):
            with self.assertRaises(NoBoard):
                generate(1, n, k=k)


class TestTheBoards(unittest.TestCase):
    def test_pinned(self):
        for (seed, n, k), want in PINNED.items():
            self.assertEqual(generate(seed, n, k=k).digest(), want, (seed, n, k))

    def test_one_answer_k_cats_everywhere_none_touching(self):
        for n, k in LEVELS:
            for seed in range(4):
                b = generate(seed, n, k=k)
                with self.subTest(n=n, k=k, seed=seed):
                    self.assertEqual(solve.count_k(n, k, b.regions, limit=3), 1)
                    cs = cells(b)
                    self.assertEqual(len(cs), n * k)
                    for line in range(n):
                        self.assertEqual(sum(r == line for r, _ in cs), k)
                        self.assertEqual(sum(c == line for _, c in cs), k)
                    for g in range(1, n + 1):
                        self.assertEqual(sum(b.regions[r * n + c] == g for r, c in cs), k)
                    for (r1, c1) in cs:
                        for (r2, c2) in cs:
                            if (r1, c1) != (r2, c2):
                                self.assertFalse(abs(r1 - r2) <= 1 and abs(c1 - c2) <= 1)

    def test_every_placement_the_solver_yields_keeps_every_rule(self):
        """Checked by a second, plain reading of the rules. A two-column stripe
        map has rows' and columns' worth of placements but no valid one (4
        regions can't hold 16 cats two apiece), so anything yielded there is a
        solver breaking a rule; a real board's one placement is checked too."""
        from itertools import islice

        n, k = 8, 2
        stripes = tuple(1 + c // 2 for r in range(n) for c in range(n))
        self.assertEqual(list(islice(solve.solutions_k(n, k, stripes), 5)), [])
        b = generate(7, n, k=k)
        for placement in islice(solve.solutions_k(n, k, b.regions), 5):
            cs = [(r, c) for r, row in enumerate(placement) for c in row]
            for g in set(b.regions):
                self.assertEqual(sum(b.regions[r * n + c] == g for r, c in cs), k)

    def test_a_k_board_with_two_answers_is_never_handed_out(self):
        from unittest import mock

        with mock.patch("catgrid.board._repair_k", return_value=True), \
                mock.patch("catgrid.solve.count_k", return_value=2):
            with self.assertRaises(NoBoard):
                generate(11, 8, tries=3, k=2)

    def test_the_general_solver_agrees_with_the_one_cat_solver(self):
        for seed in range(8):
            b = generate(seed, 6)
            self.assertEqual(solve.count_k(6, 1, b.regions, 3), solve.count(6, b.regions, 3))
            self.assertEqual(next(solve.solutions_k(6, 1, b.regions)),
                             tuple((c,) for c in b.solution))

    def test_one_cat_boards_are_the_bytes_they_were(self):
        self.assertNotIn(b'"k"', generate(7, 6).canon())


class TestPlayingThem(unittest.TestCase):
    def setUp(self):
        self.g = Game.new(7, 8, 2)

    def test_two_right_cats_in_a_row(self):
        (c1, c2) = self.g.board.solution[0]
        self.g.step(("cat", address(0, c1)))
        self.g.step(("cat", address(0, c2)))
        self.assertEqual(self.g.hearts, HEARTS)

    def test_a_touching_cat_is_wrong(self):
        c = self.g.board.solution[0][0]
        self.g.step(("cat", address(0, c)))
        near = address(0, c + 1) if c + 1 < 8 else address(0, c - 1)
        self.g.step(("cat", near))
        self.assertEqual(self.g.hearts, HEARTS - 1)

    def test_won_only_with_every_cat(self):
        cs = cells(self.g.board)
        for r, c in cs[:-1]:
            self.g.step(("cat", address(r, c)))
        self.assertEqual(self.g.status, "playing")
        self.g.step(("cat", address(*cs[-1])))
        self.assertEqual(self.g.status, "won")
        with self.assertRaises(Refused):
            self.g.step(("hint",))

    def test_hints_find_every_cat(self):
        g = Game.new(5, 8, 2, bank=[{"id": f"t:{i}", "question": f"Q{i}?", "answer": f"A{i}."}
                                     for i in range(6)])
        while g.status == "playing":
            if not g.hints["free"] + g.hints["earned"]:
                g.step(("trivia",))
                g.step(("answer", g.question["right"]))
            g.step(("hint",))
        self.assertEqual((g.status, g.hearts), ("won", HEARTS))


class TestTheirRecords(unittest.TestCase):
    def test_a_two_cat_game_replays(self):
        g = Game.new(7, 8, 2)
        g.step(("hint",))
        g.step(("cat", "A1"))
        (rec,) = [r for c, _, r in soil.records(g) if c == soil.GAMES]
        self.assertEqual(rec["k"], 2)
        self.assertEqual(soil.replay(rec).state(), g.state())

    def test_an_older_record_without_k_is_one_cat(self):
        g = Game.new(7, 6)
        g.step(("hint",))
        (rec,) = [r for c, _, r in soil.records(g) if c == soil.GAMES]
        del rec["k"]
        self.assertEqual(soil.replay(rec).state(), g.state())
