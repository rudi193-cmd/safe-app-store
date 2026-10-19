"""The rules (play.py R1-R8), each by the move it forbids: the move is refused
or costs what the rule says, and a refused move leaves the game as it was."""
from __future__ import annotations

import copy
import json
import unittest

from catgrid.board import address
from catgrid.play import HEARTS, Game, Refused


def answer(g: Game) -> list:
    return [address(r, c) for r, c in enumerate(g.board.solution)]


def wrong(g: Game) -> list:
    right = set(answer(g))
    return [a for a in g.board.addresses() if a not in right]


class Base(unittest.TestCase):
    def setUp(self):
        self.g = Game.new(7, 6)

    def refused(self, move):
        before = copy.deepcopy(self.g.state())
        with self.assertRaises(Refused):
            self.g.step(move)
        self.assertEqual(self.g.state(), before)


class TestRules(Base):
    def test_R1_a_cell_off_the_board(self):
        for move in (("cat", "Z9"), ("cat", "A7"), ("x", "G1"), ("cat", "")):
            self.refused(move)

    def test_a_move_that_isnt_one(self):
        for move in (("eat", "A1"), ("cat",), "cat A1", None, ("cat", "A1", "B2"),
                     ("cat", ["A1"]), ("hint", "A1"), ("answer",)):
            self.refused(move)

    def test_R2_a_right_cat_stays(self):
        a = answer(self.g)[0]
        self.g.step(("cat", a))
        self.assertEqual((self.g.cells[a], self.g.hearts), ("cat", HEARTS))

    def test_R3_a_wrong_cat_costs_a_heart_and_is_not_placed(self):
        a = wrong(self.g)[0]
        self.g.step(("cat", a))
        self.assertEqual((self.g.cells[a], self.g.hearts), ("", HEARTS - 1))

    def test_R3_a_cat_touching_a_right_one_is_wrong(self):
        right = answer(self.g)[0]  # row A
        self.g.step(("cat", right))
        r, c = 1, self.g.board.solution[0]  # straight below it, in row B
        touching = address(r, c + 1 if c + 1 < 6 else c - 1)
        self.g.step(("cat", touching))
        self.assertEqual(self.g.hearts, HEARTS - 1)

    def test_R4_marks_are_free(self):
        a = wrong(self.g)[0]
        self.g.step(("x", a))
        self.assertEqual((self.g.cells[a], self.g.hearts), ("x", HEARTS))
        self.g.step(("clear", a))
        self.assertEqual(self.g.cells[a], "")

    def test_R5_nothing_goes_on_a_cat(self):
        a = answer(self.g)[0]
        self.g.step(("cat", a))
        for move in (("cat", a), ("x", a), ("clear", a)):
            self.refused(move)

    def test_R5_no_clearing_what_isnt_marked_and_no_cat_on_a_mark(self):
        a = answer(self.g)[0]
        self.refused(("clear", a))
        self.g.step(("x", a))
        self.refused(("x", a))
        self.refused(("cat", a))

    def test_R6_three_wrong_cats_lose(self):
        for a in wrong(self.g)[:HEARTS]:
            self.g.step(("cat", a))
        self.assertEqual((self.g.hearts, self.g.status), (0, "lost"))

    def test_R7_every_cat_placed_wins(self):
        for a in answer(self.g):
            self.g.step(("cat", a))
        self.assertEqual(self.g.status, "won")

    def test_R8_nothing_moves_after_the_end(self):
        for a in answer(self.g):
            self.g.step(("cat", a))
        self.assertEqual(self.g.legal_moves(), [])
        self.refused(("x", wrong(self.g)[0]))


class TestWhatThePlayerSees(Base):
    def test_the_answer_is_never_in_the_view(self):
        view = json.dumps(self.g.state())
        self.assertNotIn("solution", view)
        self.assertEqual(set(self.g.state()), {"n", "regions", "cells", "hearts", "status",
                                               "hints", "trivia", "napkins"})

    def test_legal_moves_change_nothing(self):
        before = copy.deepcopy(self.g.state())
        self.assertEqual(self.g.legal_moves(), self.g.legal_moves())
        self.assertEqual(self.g.state(), before)

    def test_every_legal_move_is_accepted(self):
        for move in self.g.legal_moves():
            Game.new(7, 6).step(move)


class TestSameMovesSameGame(unittest.TestCase):
    def test_replay(self):
        def play():
            g, trace = Game.new(11, 6), []
            for i, move in enumerate(g.legal_moves()[::7]):
                if g.status != "playing":
                    break
                try:
                    trace.append(g.step(move))
                except Refused as e:
                    trace.append(str(e))
                trace.append(json.dumps(g.state(), sort_keys=True))
            return trace

        self.assertEqual(play(), play())
