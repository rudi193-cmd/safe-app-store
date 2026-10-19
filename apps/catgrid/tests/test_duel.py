"""catgrid for two: one board, turns in order, public cats, private marks.
Each rule (D1-D9, catgrid/duel.py) by the move it forbids."""
from __future__ import annotations

import copy
import json
import random
import unittest

from catgrid.duel import Duel, replay
from catgrid.play import HEARTS, Refused


def answer(d):
    return sorted(d.cats)


def wrong(d):
    return next(a for a in d._cells() if a not in d.cats and a not in d.placed
                and a not in d.marks[d.turn])


class TestTurns(unittest.TestCase):
    def setUp(self):
        self.d = Duel(3, 6)

    def test_seat_0_moves_first_and_out_of_turn_is_refused(self):  # D1
        self.assertEqual(self.d.current(), 0)
        self.assertEqual(self.d.legal_moves(1), [])
        with self.assertRaisesRegex(Refused, "turn"):
            self.d.step(1, ("x", "A1"))

    def test_every_move_passes_the_turn_a_mark_included(self):  # D1
        self.d.step(0, ("x", wrong(self.d)))
        self.assertEqual(self.d.current(), 1)
        self.d.step(1, ("cat", answer(self.d)[0]))
        self.assertEqual(self.d.current(), 0)

    def test_a_seat_out_of_hearts_is_skipped(self):  # D1, D4
        d = self.d
        for _ in range(HEARTS):
            d.step(0, ("cat", wrong(d)))
            if d.hearts[0]:
                d.step(1, ("x", wrong(d)))
        self.assertEqual(d.hearts[0], 0)
        self.assertEqual(d.current(), 1)
        d.step(1, ("x", wrong(d)))
        self.assertEqual(d.current(), 1)
        with self.assertRaisesRegex(Refused, "turn"):
            d.step(0, ("x", wrong(d)))

    def test_bad_seats_are_refused(self):
        for bad in (2, -1, True, "0"):
            with self.assertRaises(Refused):
                self.d.step(bad, ("hint",))
            with self.assertRaises(Refused):
                self.d.observe(bad)


class TestCatsAndMarks(unittest.TestCase):
    def setUp(self):
        self.d = Duel(3, 6)

    def test_a_right_cat_is_public_and_scores_for_the_mover(self):  # D3
        a = answer(self.d)[0]
        self.d.step(0, ("cat", a))
        self.assertEqual(self.d.score, [1, 0])
        self.assertEqual(self.d.observe(1).get("cells")[a], "cat")
        self.assertEqual(self.d.observe(1)["placed_by"], {a: 0})

    def test_a_wrong_cat_is_not_placed_and_costs_a_heart(self):  # D4
        a = wrong(self.d)
        self.d.step(0, ("cat", a))
        self.assertEqual(self.d.hearts, [HEARTS - 1, HEARTS])
        self.assertNotIn(a, self.d.placed)

    def test_a_mark_is_the_seats_own(self):  # D5
        a = wrong(self.d)
        said = self.d.step(0, ("x", a))
        self.assertEqual(self.d.observe(0)["cells"][a], "x")
        self.assertEqual(self.d.observe(1)["cells"][a], "")
        self.assertNotIn(a, " ".join(said))  # the narration doesn't name it either
        with self.assertRaisesRegex(Refused, "no mark"):
            self.d.step(1, ("clear", a))

    def test_no_mark_on_a_cat_and_a_cat_clears_every_mark_under_it(self):  # D5
        a = answer(self.d)[0]
        self.d.step(0, ("x", a))
        self.d.step(1, ("cat", a))
        self.assertNotIn(a, self.d.marks[0])
        with self.assertRaisesRegex(Refused, "already holds"):
            self.d.step(0, ("x", a))

    def test_the_answer_is_in_no_view(self):
        v = json.dumps([self.d.observe(0), self.d.observe(1)])
        self.assertNotIn("solution", v)
        self.assertEqual(json.loads(v)[0]["cells"], self.d.observe(0)["cells"])


class TestHints(unittest.TestCase):
    def test_a_hint_places_for_nobody_once_per_seat(self):  # D6
        d = Duel(3, 6)
        d.step(0, ("hint",))
        self.assertEqual(d.score, [0, 0])
        self.assertEqual(list(d.placed.values()), [None])
        d.step(1, ("x", wrong(d)))
        self.assertNotIn(("hint",), d.legal_moves(0))
        with self.assertRaisesRegex(Refused, "no hint"):
            d.step(0, ("hint",))


class TestTheEnd(unittest.TestCase):
    def test_it_ends_when_every_cat_is_placed_and_the_top_score_wins(self):  # D7, D8
        d = Duel(3, 6)
        for a in answer(d):
            d.step(d.current(), ("cat", a))
        self.assertTrue(d.over)
        self.assertEqual(d.score, [3, 3])
        self.assertEqual(d.winners(), [0, 1])  # a tie is both
        with self.assertRaisesRegex(Refused, "over"):
            d.step(d.current(), ("hint",))
        self.assertEqual(d.legal_moves(0), [])

    def test_a_lead_wins_alone(self):  # D8
        d = Duel(3, 6)
        cats = answer(d)
        d.step(0, ("cat", cats[0]))
        d.step(1, ("x", wrong(d)))
        for a in cats[1:]:
            d.step(d.current(), ("cat", a))
        self.assertEqual(d.winners(), [0])

    def test_both_out_ends_it_and_no_score_is_no_winner(self):  # D7, D8
        d = Duel(3, 6)
        while not d.over:
            d.step(d.current(), ("cat", wrong(d)))
        self.assertEqual(d.hearts, [0, 0])
        self.assertEqual(d.winners(), [])


class TestRefusedChangesNothing(unittest.TestCase):  # D9
    def test_every_refusal_leaves_the_duel_as_it_was(self):
        d = Duel(3, 6)
        d.step(0, ("x", "A1"))
        before = copy.deepcopy(d.__dict__)
        for seat, move in ((0, ("x", "B1")), (1, ("x", "Z9")), (1, ("cat",)), (1, "cat"),
                           (1, ("stroke", "A1")), (1, ("clear", "A1")), (1, ("x", 5))):
            with self.assertRaises(Refused, msg=(seat, move)):
                d.step(seat, move)
            self.assertEqual(d.__dict__, before, (seat, move))


class TestRecord(unittest.TestCase):
    def play(self, seed):
        d, rng = Duel(seed, 6), random.Random(seed)
        while not d.over:
            d.step(d.current(), rng.choice(d.legal_moves(d.current())))
        return d

    def test_a_duel_replays_from_its_record(self):
        for seed in range(5):
            d = self.play(seed)
            r = replay(json.loads(json.dumps(d.record())))
            self.assertEqual((r.score, r.hearts, r.placed, r.winners()),
                             (d.score, d.hearts, d.placed, d.winners()))

    def test_a_record_for_another_board_is_refused(self):
        rec = self.play(1).record()
        with self.assertRaisesRegex(ValueError, "isn't the one"):
            replay({**rec, "seed": 2})

    def test_random_play_always_ends(self):
        for seed in range(20):
            self.assertTrue(self.play(seed).over)


if __name__ == "__main__":
    unittest.main()
