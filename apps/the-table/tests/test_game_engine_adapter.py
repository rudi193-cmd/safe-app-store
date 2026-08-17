"""Drives SceneSession as a GameSession, end to end, across several seeds --
the THIRD adapter, reusing apps/game's dice-resolution rule (Engine.roll),
plugged into the SAME run_session / LedgerSink bureau and crazy_eights use,
unchanged. Also proves the two hardest guarantees named in the adapter's
module docstring: (1) apps/game/engine_state.json is never created or
modified by a scene run, no matter how many CHAOS_BURST beats it hits, and
(2) determinism comes entirely from seeding the global random module in
reset(), documented as a coupling of engine_v1_7.py itself.

Run with: python3 -m unittest discover -s tests -t . (from apps/the-table/)
"""
from __future__ import annotations

import copy
import json
import os
import random
import shutil
import tempfile
import unittest

from the_table.game_engine_adapter import SceneSession, _STAT_MAP
from the_table.game_session import GameSession, Observation, Result
from the_table.gm import first_legal_policy, random_policy, run_session

SEEDS = (0, 1, 2, 3, 7, 15, 42, 100)
DEFAULT_BEATS = 6

# apps/game/engine_state.json, resolved the same way game_engine_adapter.py
# resolves apps/game itself (repo root three parents up from this test file:
# apps/the-table/tests/test_game_engine_adapter.py -> repo root).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_ENGINE_STATE_PATH = os.path.join(_REPO_ROOT, "apps", "game", "engine_state.json")


def _assert_json_roundtrip(testcase: unittest.TestCase, value, label: str) -> None:
    encoded = json.dumps(value)
    decoded = json.loads(encoded)
    testcase.assertEqual(
        json.dumps(decoded), encoded,
        f"{label} did not round-trip through JSON: {value!r}",
    )


def _assert_observation_serializable(testcase: unittest.TestCase, obs: Observation) -> None:
    _assert_json_roundtrip(testcase, obs.view, "Observation.view")
    for line in obs.narration:
        testcase.assertIsInstance(line, str)


class _EngineStateSnapshot:
    """Existence + mtime + bytes of apps/game/engine_state.json, so a test
    can assert nothing about it changed across a scene run."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.existed = os.path.exists(path)
        if self.existed:
            self.mtime_ns = os.stat(path).st_mtime_ns
            with open(path, "rb") as f:
                self.data = f.read()
        else:
            self.mtime_ns = None
            self.data = None

    def assert_unchanged(self, testcase: unittest.TestCase) -> None:
        now_exists = os.path.exists(self.path)
        testcase.assertEqual(
            self.existed, now_exists,
            "apps/game/engine_state.json existence changed across a scene run "
            f"(was existed={self.existed}, now existed={now_exists})",
        )
        if self.existed:
            testcase.assertEqual(
                self.mtime_ns, os.stat(self.path).st_mtime_ns,
                "apps/game/engine_state.json mtime changed -- a scene run must never touch it",
            )
            with open(self.path, "rb") as f:
                now_data = f.read()
            testcase.assertEqual(
                self.data, now_data,
                "apps/game/engine_state.json bytes changed -- a scene run must never write it",
            )


class TestSceneSessionIsAGameSession(unittest.TestCase):
    def test_isinstance_protocol_check(self):
        session = SceneSession()
        self.assertIsInstance(session, GameSession)

    def test_structural_methods_exist(self):
        session = SceneSession()
        for name in ("reset", "current_seat", "observe", "legal_moves", "step",
                     "is_terminal", "result"):
            self.assertTrue(hasattr(session, name), name)
            self.assertTrue(callable(getattr(session, name)), name)
        self.assertTrue(hasattr(session, "seats"))
        self.assertEqual(session.seats, 1)


class TestSceneSessionFullScene(unittest.TestCase):
    def _play(self, seed: int, beats: int = DEFAULT_BEATS):
        """Drive a full scene deterministically from ``seed`` with a seeded
        random policy over legal_moves(). Returns (session, statuses, steps)."""
        session = SceneSession(beats=beats)
        obs = session.reset(seed)
        _assert_observation_serializable(self, obs)

        rng = random.Random(seed)
        statuses = []
        steps = 0
        while not session.is_terminal():
            self.assertLess(steps, beats + 1, f"seed {seed}: overran expected beat count")
            seat = session.current_seat()
            self.assertEqual(seat, 0)
            legal = session.legal_moves(seat)
            self.assertEqual(len(legal), 4)
            move = rng.choice(legal)
            _assert_json_roundtrip(self, move, f"seed {seed} step {steps} move")
            obs = session.step(seat, move)
            _assert_observation_serializable(self, obs)
            statuses.append(obs.view["last_status"])
            steps += 1

        return session, statuses, steps

    def test_full_scene_reaches_terminal_and_yields_a_result(self):
        for seed in SEEDS:
            with self.subTest(seed=seed):
                session, statuses, steps = self._play(seed)
                self.assertTrue(session.is_terminal())
                self.assertEqual(steps, DEFAULT_BEATS)
                self.assertEqual(len(statuses), DEFAULT_BEATS)
                for status in statuses:
                    self.assertIn(status, ("ARCHITECT_ROLL", "SUCCESS_STANDARD", "CHAOS_BURST"))

                result = session.result()
                self.assertIsInstance(result, Result)
                self.assertIsInstance(result.winners, list)
                self.assertIsInstance(result.scores, dict)
                self.assertIsInstance(result.summary, str)
                self.assertTrue(result.summary)
                self.assertIn(result.winners, ([], [0]))
                self.assertIn(0, result.scores)
                successes = statuses.count("ARCHITECT_ROLL") + statuses.count("SUCCESS_STANDARD")
                chaos = statuses.count("CHAOS_BURST")
                self.assertEqual(result.scores[0], successes)
                self.assertEqual(result.winners, [0] if successes >= chaos else [])

    def test_custom_beats_length_is_honored(self):
        for beats in (1, 3, 10):
            with self.subTest(beats=beats):
                session, statuses, steps = self._play(seed=42, beats=beats)
                self.assertEqual(steps, beats)
                self.assertTrue(session.is_terminal())

    def test_seats_is_one_and_current_seat_is_always_zero(self):
        session = SceneSession()
        session.reset(seed=0)
        self.assertEqual(session.seats, 1)
        while not session.is_terminal():
            self.assertEqual(session.current_seat(), 0)
            session.step(0, session.legal_moves(0)[0])

    def test_step_raises_once_terminal(self):
        session = SceneSession(beats=1)
        session.reset(seed=0)
        session.step(0, ("act", "Grit"))
        self.assertTrue(session.is_terminal())
        self.assertEqual(session.legal_moves(0), [])
        with self.assertRaises(RuntimeError):
            session.step(0, ("act", "Grit"))

    def test_step_rejects_unknown_move(self):
        session = SceneSession()
        session.reset(seed=0)
        with self.assertRaises(ValueError):
            session.step(0, ("act", "Nonexistent"))
        with self.assertRaises(ValueError):
            session.step(0, ("stare",))

    def test_wrong_seat_rejected(self):
        session = SceneSession()
        session.reset(seed=0)
        with self.assertRaises(ValueError):
            session.observe(1)
        with self.assertRaises(ValueError):
            session.legal_moves(1)

    def test_use_before_reset_raises(self):
        session = SceneSession()
        with self.assertRaises(RuntimeError):
            session.current_seat()
        with self.assertRaises(RuntimeError):
            session.legal_moves(0)
        with self.assertRaises(RuntimeError):
            session.step(0, ("act", "Grit"))
        with self.assertRaises(RuntimeError):
            session.is_terminal()
        with self.assertRaises(RuntimeError):
            session.result()


class TestSceneSessionDeterminism(unittest.TestCase):
    def _drive_status_sequence(self, seed: int, beats: int = DEFAULT_BEATS):
        session = SceneSession(beats=beats)
        session.reset(seed)
        sequence = []
        for stat in ("Grit", "Weird", "Cute", "Cool", "Grit", "Weird")[:beats]:
            obs = session.step(0, ("act", stat))
            sequence.append((obs.view["last_result"], obs.view["last_status"]))
        return sequence

    def test_same_seed_same_sequence(self):
        for seed in SEEDS:
            with self.subTest(seed=seed):
                first = self._drive_status_sequence(seed)
                second = self._drive_status_sequence(seed)
                self.assertEqual(first, second)

    def test_different_seeds_generally_differ(self):
        sequences = {seed: tuple(self._drive_status_sequence(seed)) for seed in SEEDS}
        # Not every pair need differ (dice are dice), but they must not all
        # collapse onto one sequence across this many distinct seeds.
        self.assertGreater(len(set(sequences.values())), 1, sequences)

    def test_reset_reseeds_regardless_of_prior_global_state(self):
        # Perturb the global RNG state arbitrarily before reset(), then
        # confirm reset(seed) still reproduces the same sequence -- proving
        # determinism comes from reset()'s own random.seed(seed) call, not
        # from whatever state random happened to be in beforehand.
        random.random()
        random.random()
        random.random()
        first = self._drive_status_sequence(seed=9)

        random.seed(12345)
        for _ in range(17):
            random.random()
        second = self._drive_status_sequence(seed=9)

        self.assertEqual(first, second)


class TestSceneSessionLegalMovesSideEffectFree(unittest.TestCase):
    def _snapshot(self, session: SceneSession):
        return copy.deepcopy({
            "beat": session._beat,
            "tally": session._tally,
            "last_result": session._last_result,
            "last_status": session._last_status,
            "debility_count": session._debility_count,
            "terminal": session._terminal,
            "stats": session._engine.stats,
        })

    def test_legal_moves_called_twice_is_stable_and_side_effect_free(self):
        session = SceneSession()
        session.reset(seed=3)

        before = self._snapshot(session)
        first = session.legal_moves(0)
        mid = self._snapshot(session)
        second = session.legal_moves(0)
        after = self._snapshot(session)

        self.assertEqual(first, second)
        self.assertEqual(first, [("act", "Grit"), ("act", "Weird"), ("act", "Cute"), ("act", "Cool")])
        self.assertEqual(before, mid)
        self.assertEqual(mid, after)

    def test_legal_moves_side_effect_free_mid_scene(self):
        session = SceneSession()
        session.reset(seed=11)
        session.step(0, ("act", "Grit"))
        session.step(0, ("act", "Weird"))

        before = self._snapshot(session)
        first = session.legal_moves(0)
        second = session.legal_moves(0)
        after = self._snapshot(session)

        self.assertEqual(first, second)
        self.assertEqual(before, after)


class TestSceneSessionViewAndMoveJSON(unittest.TestCase):
    def test_every_view_and_move_round_trips(self):
        session = SceneSession(beats=8)
        obs = session.reset(seed=5)
        _assert_json_roundtrip(self, obs.view, "reset() Observation.view")

        while not session.is_terminal():
            seat = session.current_seat()
            for move in session.legal_moves(seat):
                _assert_json_roundtrip(self, move, f"legal move {move!r}")
            move = session.legal_moves(seat)[0]
            obs = session.step(seat, move)
            _assert_json_roundtrip(self, obs.view, f"step() Observation.view at beat {session._beat}")
            observed = session.observe(seat)
            _assert_json_roundtrip(self, observed.view, "observe() Observation.view")

    def test_view_shape(self):
        session = SceneSession(beats=4)
        session.reset(seed=1)
        obs = session.step(0, ("act", "Weird"))
        view = obs.view
        self.assertEqual(
            set(view.keys()),
            {"beat", "beats_total", "stats", "last_result", "last_status", "tally", "debilities"},
        )
        self.assertEqual(set(view["stats"].keys()), set(_STAT_MAP.keys()))
        self.assertEqual(view["beat"], 1)
        self.assertEqual(view["beats_total"], 4)
        self.assertIn(view["last_status"], ("ARCHITECT_ROLL", "SUCCESS_STANDARD", "CHAOS_BURST"))


class TestEngineStateFileUntouched(unittest.TestCase):
    """The key data-lane guarantee: a scene run never creates or modifies
    apps/game/engine_state.json, including scenes that hit CHAOS_BURST (and
    therefore the in-adapter debility path)."""

    def test_engine_state_json_untouched_across_a_clean_scene(self):
        snapshot = _EngineStateSnapshot(_ENGINE_STATE_PATH)
        session = SceneSession(beats=DEFAULT_BEATS)
        session.reset(seed=10)  # seed 10 -> all SUCCESS_STANDARD, no debility path taken
        while not session.is_terminal():
            session.step(0, session.legal_moves(0)[0])
        snapshot.assert_unchanged(self)

    def test_engine_state_json_untouched_across_a_scene_with_chaos_bursts(self):
        # seed=1 with beats=6, driving the fixed ("act", stat) sequence
        # below, is confirmed (by direct run) to hit at least one
        # CHAOS_BURST -- i.e. this exercises the in-adapter debility path,
        # not just the plain-success path above.
        snapshot = _EngineStateSnapshot(_ENGINE_STATE_PATH)
        session = SceneSession(beats=6)
        session.reset(seed=1)
        hit_chaos = False
        for stat in ("Grit", "Weird", "Cute", "Cool", "Grit", "Weird"):
            obs = session.step(0, ("act", stat))
            if obs.view["last_status"] == "CHAOS_BURST":
                hit_chaos = True
        self.assertTrue(session.is_terminal())
        self.assertTrue(hit_chaos, "expected seed=1 to hit at least one CHAOS_BURST beat")
        snapshot.assert_unchanged(self)

    def test_engine_state_json_untouched_across_many_seeds(self):
        snapshot = _EngineStateSnapshot(_ENGINE_STATE_PATH)
        for seed in SEEDS:
            session = SceneSession(beats=DEFAULT_BEATS)
            session.reset(seed)
            while not session.is_terminal():
                session.step(0, session.legal_moves(0)[0])
        snapshot.assert_unchanged(self)


class TestSceneSessionLedgerIntegration(unittest.TestCase):
    def test_scene_driven_by_gm_loop_reaches_terminal_and_ledger_verifies(self):
        """The third game, through the IDENTICAL run_session + LedgerSink
        bureau and crazy_eights use, unchanged -- this is the proof the
        protocol generalizes to a freeform narrative scene too."""
        from the_table.ledger_sink import LedgerSink

        snapshot = _EngineStateSnapshot(_ENGINE_STATE_PATH)
        box_dir = tempfile.mkdtemp(prefix="the-table-test-scene-")
        try:
            game = SceneSession(beats=DEFAULT_BEATS)
            sink = LedgerSink(box_dir=box_dir)
            try:
                policy = random_policy(random.Random(4))
                result = run_session(
                    game, policy, seed=4, sink=sink, max_turns=DEFAULT_BEATS + 1,
                    session_id="test-gm-scene-integration",
                )
                self.assertTrue(game.is_terminal())
                self.assertIsInstance(result, Result)
                self.assertTrue(sink.verify(), sink._last_verify_output)
            finally:
                sink.close()
        finally:
            shutil.rmtree(box_dir, ignore_errors=True)

        snapshot.assert_unchanged(self)

    def test_scene_driven_by_first_legal_policy_also_verifies(self):
        from the_table.ledger_sink import LedgerSink

        box_dir = tempfile.mkdtemp(prefix="the-table-test-scene-firstlegal-")
        try:
            game = SceneSession(beats=DEFAULT_BEATS)
            sink = LedgerSink(box_dir=box_dir)
            try:
                policy = first_legal_policy()
                result = run_session(
                    game, policy, seed=2, sink=sink, max_turns=DEFAULT_BEATS + 1,
                    session_id="test-gm-scene-firstlegal",
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
