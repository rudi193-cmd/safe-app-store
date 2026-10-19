"""HeartsSession: game-lab's Hearts one hand at a time, with each rule tested
by the move it forbids, and the restated trick and moon rules held to
game-lab's own ``play_hand``.

Run with: python3 -m unittest discover -s tests -t . (from apps/the-table/)
"""
from __future__ import annotations

import copy
import json
import random
import unittest

from the_table import registry
from the_table.game_session import GameSession
from the_table.hearts_adapter import HeartsSession, moon, trick_winner

import hearts as gl  # noqa: E402  (on sys.path through the adapter's shim)


def passed(seed):
    """A session past its pass phase, every seat passing its three highest cards."""
    s = HeartsSession()
    s.reset(seed)
    for seat in range(4):
        top = s._hands[seat][-3:]
        s.step(seat, ("pass", *[list(c) for c in top]))
    return s


class TestTheProtocol(unittest.TestCase):
    def test_it_is_a_four_seat_game_session(self):
        self.assertIsInstance(HeartsSession(), GameSession)
        self.assertIsInstance(registry.make("hearts"), HeartsSession)

    def test_random_hands_end_with_every_point_counted(self):
        for seed in range(12):
            s, rng = HeartsSession(), random.Random(seed)
            s.reset(seed)
            while not s.is_terminal():
                seat = s.current_seat()
                for other in range(4):
                    if other != seat:
                        self.assertEqual(s.legal_moves(other), [])
                move = rng.choice(s.legal_moves(seat))
                self.assertEqual(json.loads(json.dumps(move)), list(move))
                obs = s.step(seat, move)
                self.assertEqual(json.loads(json.dumps(obs.view)), obs.view)
            pts = sorted(s.result().scores.values())
            self.assertIn(sum(pts), (26.0, 78.0))  # 26 points, or a moon's 3 x 26
            self.assertEqual(sum(s._taken), 13)


class TestHiddenHands(unittest.TestCase):
    def test_a_view_shows_its_own_hand_and_pass_only(self):
        s = HeartsSession()
        s.reset(4)
        mine = s._hands[0][:3]
        s.step(0, ("pass", *[list(c) for c in mine]))
        for seat in range(1, 4):
            v = s.observe(seat).view
            self.assertIsNone(v["my_pass"])
            self.assertEqual(v["hand"], [list(c) for c in s._hands[seat]])
            text = json.dumps(v)
            for c in s._hands[0]:
                if c not in s._hands[seat]:
                    self.assertNotIn(json.dumps(list(c)), text.replace(json.dumps(v["hand"]), ""))
        self.assertEqual(s.observe(0).view["my_pass"], [list(c) for c in mine])

    def test_passes_go_left(self):
        s = HeartsSession()
        s.reset(5)
        chosen = {seat: s._hands[seat][:3] for seat in range(4)}
        for seat in range(4):
            s.step(seat, ("pass", *[list(c) for c in chosen[seat]]))
        for seat in range(4):
            for c in chosen[seat]:
                self.assertIn(c, s._hands[(seat + 1) % 4])


class TestTheRulesItRefuses(unittest.TestCase):
    def test_out_of_turn(self):
        s = HeartsSession()
        s.reset(1)
        with self.assertRaisesRegex(ValueError, "turn"):
            s.step(2, s.legal_moves(0)[0])

    def test_a_pass_of_cards_not_held_or_repeated(self):
        s = HeartsSession()
        s.reset(1)
        other = s._hands[1][0]
        own = s._hands[0]
        for bad in ([own[0], own[1], list(other)], [own[0], own[0], own[1]]):
            with self.assertRaises(ValueError):
                s.step(0, ("pass", *[list(c) for c in bad]))
        self.assertIsNone(s._passes[0])

    def test_the_2_of_clubs_must_lead(self):
        s = passed(2)
        leader = s.current_seat()
        self.assertEqual(s.legal_moves(leader), [("play", [2, "C"])])
        other = next(c for c in s._hands[leader] if c != (2, "C"))
        with self.assertRaisesRegex(ValueError, "not a legal play"):
            s.step(leader, ("play", list(other)))

    def test_must_follow_suit(self):
        s = passed(2)
        s.step(s.current_seat(), ("play", [2, "C"]))
        seat = s.current_seat()
        off = [c for c in s._hands[seat] if c[1] != "C"]
        if any(c[1] == "C" for c in s._hands[seat]) and off:
            with self.assertRaisesRegex(ValueError, "not a legal play"):
                s.step(seat, ("play", list(off[0])))
        self.assertTrue(all(m[1][1] == "C" for m in s.legal_moves(seat))
                        or not any(c[1] == "C" for c in s._hands[seat]))

    def test_a_play_move_in_the_pass_phase_and_junk(self):
        s = HeartsSession()
        s.reset(1)
        for bad in (("play", [2, "C"]), ("pass",), "pass", (), ("pass", 1, 2, 3)):
            with self.assertRaises(ValueError, msg=bad):
                s.step(0, bad)

    def test_nothing_after_the_end(self):
        s, rng = HeartsSession(), random.Random(0)
        s.reset(0)
        while not s.is_terminal():
            s.step(s.current_seat(), rng.choice(s.legal_moves(s.current_seat())))
        self.assertEqual(s.legal_moves(s.result().winners[0]), [])
        with self.assertRaises(RuntimeError):
            s.step(0, ("play", [2, "C"]))


class TestTheRestatedRulesAreGameLabs(unittest.TestCase):
    """The named middle for trick_winner and moon: the same post-pass deal,
    played by game-lab's deterministic 'john' policy, scores the same here as
    in game-lab's own play_hand."""

    def test_same_deal_same_points_as_play_hand(self):
        for seed in range(40):
            s = passed(seed)
            theirs = gl.play_hand(copy.deepcopy(s._hands), "john")
            while not s.is_terminal():
                seat = s.current_seat()
                legal = gl.legal_plays(s._hands[seat], s._trick, s._broken, s._tricks == 0)
                card = gl.play_john(legal, s._trick, s._hands[seat])
                s.step(seat, ("play", list(card)))
            self.assertEqual(s._final, theirs, seed)

    def test_the_highest_of_the_suit_led_wins(self):
        self.assertEqual(trick_winner([(0, (5, "C")), (1, (14, "H")), (2, (9, "C")), (3, (2, "C"))]), 2)

    def test_the_moon(self):
        self.assertEqual(moon([26, 0, 0, 0], [13, 0, 0, 0], [True, False, False, False]),
                         [0, 26, 26, 26])
        self.assertEqual(moon([25, 1, 0, 0], [12, 1, 0, 0], [True, False, False, False]),
                         [25, 1, 0, 0])


if __name__ == "__main__":
    unittest.main()
