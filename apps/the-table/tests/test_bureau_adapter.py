"""Drives BureauSession as a GameSession, end to end, across several seeds.

Run with: python3 -m unittest discover -s tests -t . (from apps/the-table/)
"""
from __future__ import annotations

import json
import random
import unittest

from the_table.bureau_adapter import BureauSession
from the_table.game_session import GameSession, Observation, Result

SEEDS = (0, 1, 2, 7, 42)
STEP_CAP = 500  # bureau needs 8 visits to exhaust surprise, then a 3-9 visit
# dwell before a napkin appears (and a grape resets the dwell clock), so a
# random walk needs real headroom -- 500 is generous slack over the worst case.


class TestBureauSessionIsAGameSession(unittest.TestCase):
    def test_isinstance_protocol_check(self):
        session = BureauSession()
        self.assertIsInstance(session, GameSession)

    def test_structural_methods_exist(self):
        session = BureauSession()
        for name in ("reset", "current_seat", "observe", "legal_moves", "step",
                     "is_terminal", "result"):
            self.assertTrue(hasattr(session, name), name)
            self.assertTrue(callable(getattr(session, name)), name)
        self.assertTrue(hasattr(session, "seats"))


class TestBureauSessionFullGame(unittest.TestCase):
    def _play(self, seed: int) -> tuple[BureauSession, int]:
        """Drive a full game deterministically from ``seed``. Returns the
        session and the number of steps taken."""
        session = BureauSession()
        obs = session.reset(seed)
        self._assert_observation_serializable(obs)

        rng = random.Random(seed)
        steps = 0
        while not session.is_terminal():
            self.assertLess(steps, STEP_CAP, f"seed {seed}: did not reach terminal within cap")
            legal = session.legal_moves(session.current_seat())
            self.assertTrue(legal, f"seed {seed}: no legal moves while non-terminal")

            # Once holding a napkin, close the game out deterministically by
            # handing it to the office that can act on it, instead of hoping
            # the random walk stumbles onto it -- this is still a legal move
            # from legal_moves(), just a targeted choice among them.
            held = obs.view.get("held", [])
            if "napkin_word" in held:
                move = ("hand", "hanz")
            elif "napkin_blank" in held:
                move = ("hand", "records")
            else:
                move = rng.choice(legal)

            self._assert_json_roundtrip(move, f"seed {seed} step {steps} move")
            obs = session.step(session.current_seat(), move)
            self._assert_observation_serializable(obs)
            steps += 1

        return session, steps

    def _assert_observation_serializable(self, obs: Observation) -> None:
        self._assert_json_roundtrip(obs.view, "Observation.view")
        for line in obs.narration:
            self.assertIsInstance(line, str)

    def _assert_json_roundtrip(self, value, label: str) -> None:
        encoded = json.dumps(value)
        decoded = json.loads(encoded)
        # Round-trip through JSON is the property that matters (tuples become
        # lists, dict int-keys become strings) -- exact type equality is not
        # required, only that the value survives a snapshot.
        self.assertEqual(
            json.dumps(decoded), encoded,
            f"{label} did not round-trip through JSON: {value!r}",
        )

    def test_full_game_reaches_terminal_and_yields_a_result(self):
        for seed in SEEDS:
            with self.subTest(seed=seed):
                session, steps = self._play(seed)
                self.assertTrue(session.is_terminal())
                self.assertGreater(steps, 0)

                result = session.result()
                self.assertIsInstance(result, Result)
                self.assertIsInstance(result.winners, list)
                self.assertIsInstance(result.scores, dict)
                self.assertIsInstance(result.summary, str)
                self.assertTrue(result.summary)
                for w in result.winners:
                    self.assertIn(w, (0,))
                # bureau's Session only ever resolves to "enrolled" or
                # "voided" (play.py hand()); both are wins for the lone seat.
                self.assertEqual(result.winners, [0])
                self.assertEqual(result.scores, {0: 1.0})

    def test_seats_is_one_and_current_seat_is_always_zero(self):
        session = BureauSession()
        session.reset(seed=0)
        self.assertEqual(session.seats, 1)
        self.assertEqual(session.current_seat(), 0)

    def test_observe_does_not_advance_state(self):
        session = BureauSession()
        session.reset(seed=3)
        before = session.observe(0)
        after = session.observe(0)
        self.assertEqual(before.view, after.view)
        self.assertEqual(before.terminal, after.terminal)

    def test_unknown_move_raises(self):
        session = BureauSession()
        session.reset(seed=0)
        with self.assertRaises(ValueError):
            session.step(0, ("fly",))

    def test_wrong_seat_raises(self):
        session = BureauSession()
        session.reset(seed=0)
        with self.assertRaises(ValueError):
            session.step(1, ("look",))


if __name__ == "__main__":
    unittest.main()
