"""CheckersSession: game-lab's checkers one move at a time; each rule tested by
the move it forbids; the restated ending held to game-lab's own checkers_once.

Run with: python3 -m unittest discover -s tests -t . (from apps/the-table/)
"""
from __future__ import annotations

import json
import random
import unittest

from the_table import registry
from the_table.checkers_adapter import CheckersSession
from the_table.game_session import GameSession

import baseline_core as gl  # noqa: E402  (on sys.path through the adapter's shim)


def fresh():
    s = CheckersSession()
    s.reset(0)
    return s


def wire(mv):
    sq, e, caps, fp = mv
    return ["move", list(sq), list(e), [list(c) for c in sorted(caps)], fp]


class TestTheProtocol(unittest.TestCase):
    def test_it_is_a_two_seat_game_session(self):
        self.assertIsInstance(CheckersSession(), GameSession)
        self.assertIsInstance(registry.make("checkers"), CheckersSession)

    def test_moves_and_views_round_trip_and_only_the_mover_moves(self):
        s, rng = fresh(), random.Random(1)
        while not s.is_terminal():
            seat = s.current_seat()
            self.assertEqual(s.legal_moves(1 - seat), [])
            move = rng.choice(s.legal_moves(seat))
            self.assertEqual(json.loads(json.dumps(move)), list(move))
            obs = s.step(seat, json.loads(json.dumps(move)))  # as it arrives off the wire
            self.assertEqual(json.loads(json.dumps(obs.view)), obs.view)


class TestTheEndingIsGameLabs(unittest.TestCase):
    """The named middle for the restated ending: the same global random stream
    picks the same moves here as in checkers_once, so the winner and the move
    count must match, seed for seed."""

    def test_same_stream_same_game(self):
        names = {"P1": [0], "P2": [1], "draw": []}
        for seed in range(40):
            random.seed(seed)
            theirs, their_moves = gl.checkers_once()
            random.seed(seed)
            s = fresh()
            while not s.is_terminal():
                seat = s.current_seat()
                s.step(seat, random.choice(s.legal_moves(seat)))
            self.assertEqual((s.result().winners, s._moves), (names[theirs], their_moves), seed)


class TestTheRulesItRefuses(unittest.TestCase):
    def test_out_of_turn(self):
        s = fresh()
        with self.assertRaisesRegex(ValueError, "turn"):
            s.step(1, s.legal_moves(0)[0])

    def test_a_move_not_in_the_list(self):
        s = fresh()
        for bad in (["move", [2, 1], [4, 3], [], "a"], ["move", [5, 0], [4, 1], [], "h"],
                    ("move",), "move", ["jump", [2, 1], [3, 0], [], "a"]):
            with self.assertRaisesRegex(ValueError, "not a legal move", msg=bad):
                s.step(0, bad)
        self.assertEqual(s._moves, 0)

    def test_a_capture_is_mandatory(self):
        s = fresh()
        s._board = {(2, 1): "a", (3, 2): "h", (2, 5): "a", (7, 0): "h"}
        legal = [list(m) for m in s.legal_moves(0)]
        self.assertEqual(legal, [wire(m) for m in gl.ck_legal(s._board, "a")])
        self.assertTrue(all(m[3] for m in legal))
        with self.assertRaisesRegex(ValueError, "mandatory"):
            s.step(0, ["move", [2, 5], [3, 6], [], "a"])

    def test_taking_the_last_piece_wins(self):
        s = fresh()
        s._board = {(2, 1): "a", (3, 2): "h"}
        s.step(0, ["move", [2, 1], [4, 3], [[3, 2]], "a"])
        self.assertEqual((s.is_terminal(), s.result().winners), (True, [0]))
        self.assertIn("took every piece", s.result().summary)

    def test_no_legal_move_loses(self):
        s = fresh()
        # h's one man on (7, 0) is walled in: (6, 1) is held, the jump to (5, 2) too
        s._board = {(7, 0): "h", (6, 1): "a", (5, 2): "a", (0, 7): "a"}
        s.step(0, ["move", [0, 7], [1, 6], [], "a"])
        self.assertEqual(gl.ck_legal(s._board, "h"), [])
        self.assertEqual((s.is_terminal(), s.result().winners), (True, [0]))
        self.assertIn("no legal move", s.result().summary)

    def test_a_quiet_game_is_adjudicated_on_material(self):
        s = fresh()
        s._board = {(0, 1): "A", (7, 6): "h", (7, 4): "h", (0, 7): "a"}
        s._quiet = 59
        s.step(0, s.legal_moves(0)[0])
        self.assertTrue(s.is_terminal())
        self.assertEqual(s.result().winners, [0])  # 2 + 1 against 1 + 1
        self.assertIn("material 3-2", s.result().summary)

    def test_even_material_is_a_draw(self):
        s = fresh()
        s._board = {(0, 1): "a", (7, 6): "h"}
        s._moves = 299
        s.step(0, s.legal_moves(0)[0])
        self.assertEqual((s.is_terminal(), s.result().winners), (True, []))

    def test_crowning_is_said(self):
        s = fresh()
        s._board = {(6, 1): "a", (0, 7): "h"}
        obs = s.step(0, ["move", [6, 1], [7, 0], [], "A"])
        self.assertIn("crowned", obs.narration[0])
        self.assertEqual(s._board[(7, 0)], "A")


if __name__ == "__main__":
    unittest.main()
