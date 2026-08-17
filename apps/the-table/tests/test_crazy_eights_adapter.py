"""Drives CrazyEightsSession as a GameSession, end to end, across several
seeds -- the second adapter, reusing game-lab's real rule logic, plugged into
the SAME run_session / LedgerSink bureau uses, unchanged.

Run with: python3 -m unittest discover -s tests -t . (from apps/the-table/)
"""
from __future__ import annotations

import copy
import json
import random
import shutil
import tempfile
import unittest

from the_table.crazy_eights_adapter import CrazyEightsSession
from the_table.game_session import GameSession, Observation, Result
from the_table.gm import random_policy, run_session

SEEDS = (0, 1, 2, 7, 42, 100)
STEP_CAP = 2000  # generous slack over the adapter's own defensive cap (1000)


class TestCrazyEightsSessionIsAGameSession(unittest.TestCase):
    def test_isinstance_protocol_check(self):
        session = CrazyEightsSession()
        self.assertIsInstance(session, GameSession)

    def test_structural_methods_exist(self):
        session = CrazyEightsSession()
        for name in ("reset", "current_seat", "observe", "legal_moves", "step",
                     "is_terminal", "result"):
            self.assertTrue(hasattr(session, name), name)
            self.assertTrue(callable(getattr(session, name)), name)
        self.assertTrue(hasattr(session, "seats"))
        self.assertEqual(session.seats, 4)


class TestCrazyEightsFullGame(unittest.TestCase):
    def _play(self, seed: int):
        """Drive a full game deterministically from ``seed`` with a seeded
        random policy over legal_moves(). Returns (session, seats_seen, steps)."""
        session = CrazyEightsSession()
        obs = session.reset(seed)
        self._assert_observation_serializable(obs)

        rng = random.Random(seed)
        seats_seen = set()
        steps = 0
        while not session.is_terminal():
            self.assertLess(steps, STEP_CAP, f"seed {seed}: did not reach terminal within cap")
            seat = session.current_seat()
            seats_seen.add(seat)
            legal = session.legal_moves(seat)
            self.assertTrue(legal, f"seed {seed}: no legal moves while non-terminal")
            move = rng.choice(legal)
            self._assert_json_roundtrip(move, f"seed {seed} step {steps} move")
            obs = session.step(seat, move)
            self._assert_observation_serializable(obs)
            steps += 1

        return session, seats_seen, steps

    def _assert_observation_serializable(self, obs: Observation) -> None:
        self._assert_json_roundtrip(obs.view, "Observation.view")
        for line in obs.narration:
            self.assertIsInstance(line, str)

    def _assert_json_roundtrip(self, value, label: str) -> None:
        encoded = json.dumps(value)
        decoded = json.loads(encoded)
        # Round-trip through JSON is the property that matters (tuples become
        # lists) -- exact type equality is not required, only that the value
        # survives a snapshot, same convention test_bureau_adapter.py uses.
        self.assertEqual(
            json.dumps(decoded), encoded,
            f"{label} did not round-trip through JSON: {value!r}",
        )

    def test_full_game_reaches_terminal_and_yields_a_result(self):
        for seed in SEEDS:
            with self.subTest(seed=seed):
                session, seats_seen, steps = self._play(seed)
                self.assertTrue(session.is_terminal())
                self.assertGreater(steps, 0)

                result = session.result()
                self.assertIsInstance(result, Result)
                self.assertIsInstance(result.winners, list)
                self.assertIsInstance(result.scores, dict)
                self.assertIsInstance(result.summary, str)
                self.assertTrue(result.summary)
                for w in result.winners:
                    self.assertIn(w, (0, 1, 2, 3))
                if result.winners:
                    self.assertEqual(len(result.winners), 1)
                    self.assertEqual(result.scores, {result.winners[0]: 1.0})
                else:
                    self.assertEqual(result.scores, {})
                    self.assertEqual(result.summary, "stalled")

    def test_multi_seat_current_seat_cycles(self):
        # Over a full game, current_seat() must visit more than one seat --
        # this is a real 4-seat game, not a relabeled single-seat one.
        _session, seats_seen, _steps = self._play(seed=7)
        self.assertGreater(len(seats_seen), 1, f"seats_seen={seats_seen}")

    def test_seats_is_four(self):
        session = CrazyEightsSession()
        session.reset(seed=0)
        self.assertEqual(session.seats, 4)
        self.assertIn(session.current_seat(), (0, 1, 2, 3))


class TestCrazyEightsLegalMovesSideEffectFree(unittest.TestCase):
    def _snapshot(self, session: CrazyEightsSession):
        return copy.deepcopy({
            "hands": session._hands,
            "stock": session._stock,
            "discard_top": session._discard_top,
            "active_suit": session._active_suit,
            "turn": session._turn,
            "consecutive_passes": session._consecutive_passes,
            "winner": session._winner,
            "terminal": session._terminal,
        })

    def test_legal_moves_called_twice_is_stable_and_side_effect_free(self):
        session = CrazyEightsSession()
        session.reset(seed=3)
        seat = session.current_seat()

        before = self._snapshot(session)
        first = session.legal_moves(seat)
        mid = self._snapshot(session)
        second = session.legal_moves(seat)
        after = self._snapshot(session)

        self.assertEqual(first, second)
        self.assertEqual(before, mid)
        self.assertEqual(mid, after)

    def test_legal_moves_side_effect_free_mid_game(self):
        # Drive a few real steps in, then check legal_moves() twice again --
        # side-effect-freedom should hold at any point in the game, not just
        # at the very start.
        session = CrazyEightsSession()
        session.reset(seed=11)
        rng = random.Random(11)
        for _ in range(10):
            if session.is_terminal():
                break
            seat = session.current_seat()
            move = rng.choice(session.legal_moves(seat))
            session.step(seat, move)

        if session.is_terminal():
            return  # nothing left to check mid-game for this seed

        seat = session.current_seat()
        before = self._snapshot(session)
        first = session.legal_moves(seat)
        second = session.legal_moves(seat)
        after = self._snapshot(session)

        self.assertEqual(first, second)
        self.assertEqual(before, after)


class TestCrazyEightsHiddenInfo(unittest.TestCase):
    def test_observe_does_not_leak_other_seats_hands(self):
        session = CrazyEightsSession()
        session.reset(seed=5)
        rng = random.Random(5)
        # Advance a handful of real steps so hands diverge from the initial
        # deal, then check hidden info holds mid-game too, not just at reset.
        for _ in range(5):
            if session.is_terminal():
                break
            seat = session.current_seat()
            move = rng.choice(session.legal_moves(seat))
            session.step(seat, move)

        other_cards = set()
        for s in range(4):
            if s == 0:
                continue
            other_cards.update(tuple(c) for c in session._hands[s])

        obs0 = session.observe(0)
        view = obs0.view

        # The view must not expose any key that could carry another seat's
        # hand -- opponents appear only through opponent_hand_sizes.
        self.assertEqual(
            set(view.keys()),
            {"seat", "hand", "discard_top", "active_suit",
             "stock_count", "opponent_hand_sizes", "current_seat"},
        )

        # No other seat's actual card appears in seat 0's own hand list --
        # the deck has no duplicate cards, so this is a structural
        # guarantee (any overlap would mean a real leak), not luck.
        own_hand_cards = {tuple(c) for c in view["hand"]}
        self.assertTrue(own_hand_cards.isdisjoint(other_cards))

        # Opponents are represented purely as counts, one per opponent.
        self.assertIsInstance(view["opponent_hand_sizes"], list)
        self.assertEqual(len(view["opponent_hand_sizes"]), 3)
        for size in view["opponent_hand_sizes"]:
            self.assertIsInstance(size, int)

        # observe(seat) round-trips through JSON like any other Observation.
        self.assertEqual(json.loads(json.dumps(view)), view)


class TestCrazyEightsLedgerIntegration(unittest.TestCase):
    def test_crazy_eights_driven_by_gm_loop_reaches_terminal_and_ledger_verifies(self):
        """The second game, through the IDENTICAL run_session + LedgerSink
        bureau uses, unchanged -- this is the proof the protocol generalizes."""
        from the_table.ledger_sink import LedgerSink

        box_dir = tempfile.mkdtemp(prefix="the-table-test-crazy8-")
        try:
            game = CrazyEightsSession()
            sink = LedgerSink(box_dir=box_dir)
            try:
                policy = random_policy(random.Random(7))
                result = run_session(
                    game, policy, seed=7, sink=sink, max_turns=STEP_CAP,
                    session_id="test-gm-crazy8-integration",
                )
                self.assertTrue(game.is_terminal())
                self.assertIsInstance(result, Result)
                self.assertTrue(sink.verify(), sink._last_verify_output)
            finally:
                sink.close()
        finally:
            shutil.rmtree(box_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
