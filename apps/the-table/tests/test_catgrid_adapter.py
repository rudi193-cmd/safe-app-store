"""Drives CatgridSession as a GameSession, end to end, across several seeds,
with the guards the other adapters carry: JSON round-trips, side-effect-free
legal_moves, the step cap, and the answer never in a view.

Run with: python3 -m unittest discover -s tests -t . (from apps/the-table/)
"""
from __future__ import annotations

import json
import random
import unittest

from the_table import registry
from the_table.catgrid_adapter import CatgridDuelSession, CatgridSession
from the_table.game_session import GameSession

SEEDS = (0, 1, 2, 7, 42)
SEATS_SEEDS = SEEDS
STEP_CAP = 2000  # up to 169 cells x (cat|x|clear) on 13x13, plus hints and trivia; a lost game ends at 3 wrong cats
BANK = [{"id": f"t:{i}", "question": f"Q{i}?", "answer": f"A{i}."} for i in range(6)]
WORDS = ["Filed.", "Sieve"]


def play(seed, session):
    obs = session.reset(seed)
    rng, steps, trace = random.Random(seed), 0, [obs.view]
    while not session.is_terminal():
        assert steps < STEP_CAP, f"seed {seed}: no terminal within the cap"
        legal = session.legal_moves(0)
        assert legal, f"seed {seed}: no legal moves while non-terminal"
        move = rng.choice(legal)
        assert json.loads(json.dumps(move)) == list(move)
        obs = session.step(0, move)
        trace.append(obs.view)
        steps += 1
    return trace


class TestCatgridIsAGameSession(unittest.TestCase):
    def test_protocol(self):
        self.assertIsInstance(CatgridSession(), GameSession)

    def test_registered(self):
        for name, (n, k) in (("catgrid", (6, 1)), ("catgrid_2cat", (9, 2)), ("catgrid_3cat", (13, 3))):
            s = registry.make(name)
            self.assertIsInstance(s, CatgridSession)
            self.assertEqual((s.n, s.k), (n, k))

    def test_the_levels_play_to_terminal(self):
        for n, k in ((9, 2), (13, 3)):
            s = CatgridSession(n=n, k=k, bank=BANK, words=WORDS)
            trace = play(1, s)
            self.assertEqual(trace[0]["k"], k)
            self.assertTrue(s.is_terminal())


class TestCatgridFullGame(unittest.TestCase):
    def test_every_seed_reaches_terminal_with_json_views(self):
        for seed in SEEDS:
            trace = play(seed, CatgridSession(bank=BANK, words=WORDS))
            for view in trace:
                self.assertEqual(json.loads(json.dumps(view)), view)
            r = CatgridSession(bank=BANK, words=WORDS)
            play(seed, r)
            self.assertIn(r.result().summary, ("solved with 1 heart(s) left",
                                               "solved with 2 heart(s) left",
                                               "solved with 3 heart(s) left",
                                               "out of hearts"))

    def test_same_seed_same_game(self):
        for seed in SEEDS:
            self.assertEqual(play(seed, CatgridSession(bank=BANK, words=WORDS)),
                             play(seed, CatgridSession(bank=BANK, words=WORDS)))

    def test_the_answer_is_never_in_a_view(self):
        s = CatgridSession(bank=BANK, words=WORDS)
        for view in play(3, s):
            self.assertNotIn("solution", json.dumps(view))
            self.assertNotIn("right", json.dumps(view))

    def test_legal_moves_change_nothing(self):
        s = CatgridSession(bank=BANK, words=WORDS)
        s.reset(11)
        before = json.dumps(s.observe(0).view)
        self.assertEqual(s.legal_moves(0), s.legal_moves(0))
        self.assertEqual(json.dumps(s.observe(0).view), before)

    def test_a_refused_move_raises_and_changes_nothing(self):
        s = CatgridSession(bank=BANK, words=WORDS)
        s.reset(11)
        before = json.dumps(s.observe(0).view)
        with self.assertRaises(ValueError):
            s.step(0, ("cat", "Z99"))
        self.assertEqual(json.dumps(s.observe(0).view), before)

    def test_seat_and_reset_are_required(self):
        with self.assertRaises(RuntimeError):
            CatgridSession().legal_moves(0)
        s = CatgridSession(bank=BANK, words=WORDS)
        s.reset(1)
        with self.assertRaises(ValueError):
            s.legal_moves(1)
