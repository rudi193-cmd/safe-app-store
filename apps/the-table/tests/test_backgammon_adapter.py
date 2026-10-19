"""BackgammonSession: game-lab's backgammon one die at a time; each rule
tested by the move it forbids; the dice the session's own, from its seed.

Run with: python3 -m unittest discover -s tests -t . (from apps/the-table/)
"""
from __future__ import annotations

import json
import random
import unittest

from the_table import registry
from the_table.backgammon_adapter import TURN_CAP, BackgammonSession
from the_table.game_session import GameSession

import baseline_core as gl  # noqa: E402  (on sys.path through the adapter's shim)


def fresh(seed=0):
    s = BackgammonSession()
    s.reset(seed)
    return s


def play(seed):
    s, rng = fresh(seed), random.Random(seed)
    while not s.is_terminal():
        seat = s.current_seat()
        legal = s.legal_moves(seat)
        assert legal, (seed, "a seat on turn with no legal move")
        s.step(seat, json.loads(json.dumps(rng.choice(legal))))
    return s


class TestTheProtocol(unittest.TestCase):
    def test_it_is_a_two_seat_game_session(self):
        self.assertIsInstance(BackgammonSession(), GameSession)
        self.assertIsInstance(registry.make("backgammon"), BackgammonSession)

    def test_random_games_end_with_fifteen_off_and_the_same_seed_replays(self):
        for seed in range(10):
            s = play(seed)
            w = s.result().winners[0]
            self.assertTrue(s._sides[w]["off"] == 15 or s._turns >= TURN_CAP)
            self.assertEqual(play(seed)._sides, s._sides)

    def test_views_round_trip(self):
        s = fresh(3)
        v = s.observe(0).view
        self.assertEqual(json.loads(json.dumps(v)), v)
        self.assertEqual(v["me"]["pips"], 167)  # the standard start


class TestDice(unittest.TestCase):
    def test_the_opening_roll_differs_and_the_higher_moves_first(self):
        for seed in range(30):
            s = fresh(seed)
            a, b = s._dice
            self.assertNotEqual(a, b)
            self.assertEqual(s.current_seat(), 0 if a > b else 1)

    def test_doubles_give_four_dice(self):
        seen = False
        for seed in range(40):
            s, rng = fresh(seed), random.Random(seed)
            while not s.is_terminal() and not seen:
                if len(s._dice) == 4:
                    seen = len(set(s._dice)) == 1
                    break
                s.step(s.current_seat(), rng.choice(s.legal_moves(s.current_seat())))
            if seen:
                break
        self.assertTrue(seen)

    def test_a_die_is_used_once(self):
        s = fresh(0)
        seat, before = s.current_seat(), list(s._dice)
        move = s.legal_moves(seat)[0]
        s.step(seat, move)
        self.assertEqual(s.current_seat(), seat)  # one die left: still this seat's turn
        rest = list(before)
        rest.remove(move[1])
        self.assertEqual(sorted(s._dice), sorted(rest))


class TestTheRulesItRefuses(unittest.TestCase):
    def test_out_of_turn_and_a_die_not_rolled(self):
        s = fresh(0)
        seat = s.current_seat()
        with self.assertRaisesRegex(ValueError, "turn"):
            s.step(1 - seat, s.legal_moves(seat)[0])
        missing = next(d for d in range(1, 7) if d not in s._dice)
        for mv in gl.bg_leg(s._sides[seat], s._sides[1 - seat], missing):
            with self.assertRaisesRegex(ValueError, "not a legal use"):
                s.step(seat, ["move", missing, *mv])

    def test_junk(self):
        s = fresh(0)
        for bad in (("move",), "move", ["move", 3, "fly", 24, 21, False], ()):
            with self.assertRaisesRegex(ValueError, "not a legal use", msg=bad):
                s.step(s.current_seat(), bad)

    def test_the_bar_comes_first(self):
        s = fresh(0)
        seat = s.current_seat()
        s._sides[seat]["bar"] = 1
        s._sides[seat]["pts"][24] -= 1
        self.assertTrue(s.legal_moves(seat))
        self.assertTrue(all(m[2] == "enter" for m in s.legal_moves(seat)))

    def test_no_bearing_off_before_home(self):
        s = fresh(0)
        seat = s.current_seat()
        self.assertFalse(any(m[2] == "off" for m in s.legal_moves(seat)))

    def test_bearing_off_the_last_checker_wins(self):
        s = fresh(0)
        seat = s.current_seat()
        s._sides[seat] = {"pts": {1: 1}, "bar": 0, "off": 14}
        s._dice = [1, 2]
        s.step(seat, ["move", 1, "off", 1, False])
        self.assertEqual((s.is_terminal(), s.result().winners), (True, [seat]))
        self.assertIn("gammon", s.result().summary)  # the other side bore off none

    def test_a_roll_that_cant_move_passes_on(self):
        s = fresh(0)
        seat = s.current_seat()
        other = 1 - seat
        # a closed board: entering on my 25-d is the other side's own point d, 1..6
        s._sides[other] = {"pts": {p: 2 for p in range(1, 7)}, "bar": 0, "off": 3}
        s._sides[seat] = {"pts": {1: 1}, "bar": 0, "off": 13}
        s._sides[seat]["bar"] = 1
        s._dice = [6]
        self.assertEqual(s._legal(seat), [])  # nothing enters a closed board
        said = []
        s._next_turn(said)
        self.assertNotEqual(s._legal(s.current_seat()), [])

    def test_the_turn_cap_adjudicates_on_pips(self):
        s = fresh(0)
        s._turns = TURN_CAP - 1
        s._sides[0] = {"pts": {1: 15}, "bar": 0, "off": 0}
        s._next_turn([])
        self.assertEqual((s.is_terminal(), s.result().winners), (True, [0]))


if __name__ == "__main__":
    unittest.main()
