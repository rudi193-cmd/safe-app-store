"""LiarsDiceSession: game-lab's Perudo rules one bid at a time; each rule
tested by the move it forbids; cups hidden until a challenge lifts them.

Run with: python3 -m unittest discover -s tests -t . (from apps/the-table/)
"""
from __future__ import annotations

import json
import random
import unittest

from the_table import registry
from the_table.game_session import GameSession
from the_table.liars_dice_adapter import LiarsDiceSession

import liars_dice as gl  # noqa: E402  (on sys.path through the adapter's shim)


def fresh(seed=3):
    s = LiarsDiceSession()
    s.reset(seed)
    return s


class TestTheProtocol(unittest.TestCase):
    def test_it_is_a_four_seat_game_session(self):
        self.assertIsInstance(LiarsDiceSession(), GameSession)
        self.assertIsInstance(registry.make("liars_dice"), LiarsDiceSession)

    def test_random_games_end_with_one_seat_holding_dice(self):
        for seed in range(15):
            s, rng = fresh(seed), random.Random(seed)
            while not s.is_terminal():
                seat = s.current_seat()
                move = rng.choice(s.legal_moves(seat))
                self.assertEqual(json.loads(json.dumps(move)), list(move))
                obs = s.step(seat, move)
                self.assertEqual(json.loads(json.dumps(obs.view)), obs.view)
            r = s.result()
            self.assertEqual(len(r.winners), 1)
            self.assertEqual(sum(1 for d in s._dice if d), 1)

    def test_the_same_seed_rolls_the_same_cups(self):
        self.assertEqual(fresh(9)._cups, fresh(9)._cups)
        self.assertNotEqual(fresh(9)._cups, fresh(10)._cups)


class TestCups(unittest.TestCase):
    def test_a_view_shows_its_own_cup_only(self):
        s = fresh()
        for seat in range(4):
            v = s.observe(seat).view
            self.assertEqual(v["my_dice"], s._cups[seat])
            self.assertIsNone(v["last_reveal"])
            self.assertNotIn("cups", json.dumps(v))

    def test_a_challenge_lifts_every_cup_for_everyone(self):
        s = fresh()
        s.step(s.current_seat(), ("bid", 1, 2))
        s.step(s.current_seat(), ("challenge",))
        for seat in range(4):
            reveal = s.observe(seat).view["last_reveal"]
            self.assertEqual(len(reveal["cups"]), 4)


class TestTheRulesItRefuses(unittest.TestCase):
    def test_the_opener_cannot_challenge(self):
        s = fresh()
        self.assertNotIn(("challenge",), s.legal_moves(s.current_seat()))
        with self.assertRaisesRegex(ValueError, "no bid"):
            s.step(s.current_seat(), ("challenge",))

    def test_a_bid_must_raise(self):
        s = fresh()
        s.step(s.current_seat(), ("bid", 3, 4))
        seat = s.current_seat()
        for q, f in ((3, 4), (3, 3), (2, 6), (21, 1), (0, 5), (3, 7), (True, 5)):
            with self.assertRaisesRegex(ValueError, "not a raise", msg=(q, f)):
                s.step(seat, ("bid", q, f))
        s.step(seat, ("bid", 3, 5))  # same quantity, higher face: a raise

    def test_out_of_turn_and_junk(self):
        s = fresh()
        other = (s.current_seat() + 1) % 4
        self.assertEqual(s.legal_moves(other), [])
        with self.assertRaisesRegex(ValueError, "turn"):
            s.step(other, ("bid", 1, 2))
        for bad in (("bid", 1), ("raise", 1, 2), "challenge", ()):
            with self.assertRaises(ValueError, msg=bad):
                s.step(s.current_seat(), bad)


class TestTheChallenge(unittest.TestCase):
    def challenge(self, s, q, f):
        bidder = s.current_seat()
        s.step(bidder, ("bid", q, f))
        challenger = s.current_seat()
        everything = [d for c in s._cups.values() for d in c]
        before = list(s._dice)
        s.step(challenger, ("challenge",))
        return bidder, challenger, gl.count_face(everything, f), before

    def test_a_true_bid_costs_the_challenger(self):
        s = fresh()
        face = s._cups[s.current_seat()][0]  # the bidder holds one: 1 x face is true
        bidder, challenger, count, before = self.challenge(s, 1, face)
        self.assertGreaterEqual(count, 1)
        self.assertEqual(s._dice[challenger], before[challenger] - 1)
        self.assertEqual(s._dice[bidder], before[bidder])

    def test_an_exact_bid_is_good_and_costs_the_challenger(self):
        s = fresh()
        everything = [d for c in s._cups.values() for d in c]
        exact = gl.count_face(everything, 4)  # the very count: "at least" holds
        self.assertGreater(exact, 0)
        bidder, challenger, count, before = self.challenge(s, exact, 4)
        self.assertEqual(count, exact)
        self.assertEqual(s._dice[challenger], before[challenger] - 1)
        self.assertEqual(s._dice[bidder], before[bidder])

    def test_a_false_bid_costs_the_bidder(self):
        s = fresh()
        bidder, challenger, count, before = self.challenge(s, 20, 6)
        self.assertLess(count, 20)
        self.assertEqual(s._dice[bidder], before[bidder] - 1)
        self.assertEqual(s._dice[challenger], before[challenger])

    def test_ones_are_wild_through_game_labs_count(self):
        s = fresh()
        _, _, count, _ = self.challenge(s, 1, 5)
        self.assertEqual(s._reveal["count"], count)
        self.assertEqual(count, sum(1 for c in s._reveal["cups"].values() for d in c if d in (1, 5)))

    def test_the_loser_opens_the_next_round_with_fresh_cups(self):
        s = fresh()
        self.challenge(s, 20, 6)
        loser = s._reveal["loser"]
        self.assertEqual(s.current_seat(), loser)
        self.assertEqual((s._bid, s._rounds), (None, 2))
        self.assertEqual(len(s._cups[loser]), s._dice[loser])

    def test_a_seat_with_no_dice_is_skipped(self):
        s = fresh()
        s._dice[1] = 0
        s._open_round(0)
        s.step(0, ("bid", 1, 2))
        self.assertEqual(s.current_seat(), 2)
        self.assertNotIn(1, s._cups)


if __name__ == "__main__":
    unittest.main()
