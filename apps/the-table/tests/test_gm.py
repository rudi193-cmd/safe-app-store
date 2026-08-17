"""tests/test_gm.py — unit tests for the GM driver loop (the_table/gm.py).

Two suites:
  * TestDriverMechanics — a trivial in-file STUB GameSession (a 2-seat
    counter) proves the driver's own mechanics (turn order via
    current_seat(), terminal stop, max_turns cap, sink call counts, return
    value) in isolation from bureau. This tests the driver, not the game.
  * TestBureauIntegration — the real BureauSession + a real LedgerSink
    (temp dir) driven through run_session with a seeded policy, asserting
    terminal is reached and ai-game-master's own verifier accepts the chain.

Run with: python3 -m unittest discover -s tests -t . (from apps/the-table/)
"""
from __future__ import annotations

import random
import shutil
import tempfile
import unittest

from the_table.game_session import Observation, Result
from the_table.gm import GMError, first_legal_policy, random_policy, run_session


# ── stub game: a 2-seat counter ─────────────────────────────────────────────
#
# Seats alternate 0, 1, 0, 1, ... (current_seat() derived from the counter's
# parity, never hardcoded by the driver). The single legal move is ("inc",);
# each step increments the counter by 1. The game is terminal once the
# counter reaches `end_at`. This is deliberately the simplest possible
# GameSession -- it exists purely to exercise run_session's own logic.
class CounterGame:
    seats = 2

    def __init__(self, end_at: int = 4):
        self.end_at = end_at
        self.counter = 0
        self.moves_seen: list = []

    def reset(self, seed: int) -> Observation:
        self.counter = 0
        self.moves_seen = []
        return self._obs()

    def current_seat(self) -> int:
        return self.counter % 2

    def observe(self, seat: int) -> Observation:
        return self._obs()

    def legal_moves(self, seat: int):
        return [("inc",)]

    def step(self, seat: int, move) -> Observation:
        assert move == ("inc",)
        self.moves_seen.append((seat, move))
        self.counter += 1
        return self._obs()

    def is_terminal(self) -> bool:
        return self.counter >= self.end_at

    def result(self) -> Result:
        return Result(
            winners=[0] if self.counter % 2 == 0 else [1],
            scores={0: float(self.counter)},
            summary=f"counter reached {self.counter}",
        )

    def _obs(self) -> Observation:
        return Observation(
            seat=self.current_seat() if not self.is_terminal() else None,
            view={"counter": self.counter},
            narration=[f"counter is now {self.counter}"],
            terminal=self.is_terminal(),
        )


# A stub that never reaches terminal, to exercise the max_turns cap path.
class NeverEndingGame(CounterGame):
    def is_terminal(self) -> bool:
        return False


# ── recording fake sink ─────────────────────────────────────────────────────
class RecordingSink:
    def __init__(self):
        self.opened: list = []
        self.snapshots: list = []
        self.closed: list = []

    def open_session(self, session_id, meta):
        self.opened.append((session_id, meta))

    def snapshot(self, state, note=""):
        self.snapshots.append((state, note))

    def close_session(self, result):
        self.closed.append(result)


class TestDriverMechanics(unittest.TestCase):
    def test_turn_order_follows_current_seat(self):
        game = CounterGame(end_at=4)
        run_session(game, first_legal_policy(), seed=0)
        self.assertEqual([seat for seat, _ in game.moves_seen], [0, 1, 0, 1])

    def test_stops_at_terminal_and_returns_result(self):
        game = CounterGame(end_at=4)
        result = run_session(game, first_legal_policy(), seed=0)
        self.assertIsInstance(result, Result)
        self.assertEqual(game.counter, 4)
        self.assertEqual(result.summary, "counter reached 4")

    def test_respects_max_turns_cap_and_raises_gmerror(self):
        game = NeverEndingGame(end_at=10**9)
        with self.assertRaises(GMError) as ctx:
            run_session(game, first_legal_policy(), seed=0, max_turns=3)
        self.assertEqual(ctx.exception.turns_taken, 3)
        self.assertIsNotNone(ctx.exception.last_observation)
        # exactly max_turns moves were actually applied to the game -- the
        # cap stops the loop, it does not fabricate extra progress.
        self.assertEqual(len(game.moves_seen), 3)

    def test_sink_is_none_works(self):
        game = CounterGame(end_at=4)
        result = run_session(game, first_legal_policy(), seed=0, sink=None)
        self.assertEqual(result.summary, "counter reached 4")

    def test_sink_open_snapshot_close_call_counts(self):
        game = CounterGame(end_at=4)
        sink = RecordingSink()
        run_session(game, first_legal_policy(), seed=0, sink=sink, session_id="s1")

        self.assertEqual(len(sink.opened), 1)
        self.assertEqual(sink.opened[0][0], "s1")
        self.assertEqual(sink.opened[0][1], {"seed": 0, "seats": 2})

        # one snapshot per turn actually taken (4 turns to reach end_at=4)
        self.assertEqual(len(sink.snapshots), 4)
        for (state, note), (seat, move) in zip(sink.snapshots, game.moves_seen):
            self.assertEqual(state["seat"], seat)
            # RecordingSink is a plain fake -- it receives run_session's raw
            # state dict, not a JSON-encoded one, so the move survives as
            # the exact tuple the policy chose. (The real LedgerSink is the
            # one that JSON-encodes it; that round-trip is covered by
            # test_ledger_sink.py and by the bureau integration test below.)
            self.assertEqual(state["move"], move)
            self.assertIn("view", state)
            self.assertIsInstance(note, str)

        self.assertEqual(len(sink.closed), 1)
        self.assertEqual(sink.closed[0]["summary"], "counter reached 4")

    def test_sink_not_closed_when_max_turns_cap_hit(self):
        # A capped run is not a finished session -- close_session must not
        # fire on a GMError, since there is no trustworthy Result to close
        # with.
        game = NeverEndingGame(end_at=10**9)
        sink = RecordingSink()
        with self.assertRaises(GMError):
            run_session(game, first_legal_policy(), seed=0, sink=sink, max_turns=2)
        self.assertEqual(len(sink.opened), 1)
        self.assertEqual(len(sink.snapshots), 2)
        self.assertEqual(len(sink.closed), 0)

    def test_random_policy_picks_only_legal_moves(self):
        game = CounterGame(end_at=20)
        policy = random_policy(random.Random(1))
        run_session(game, policy, seed=0)
        for seat, move in game.moves_seen:
            self.assertEqual(move, ("inc",))


class TestBureauIntegration(unittest.TestCase):
    def test_bureau_driven_by_gm_loop_reaches_terminal_and_ledger_verifies(self):
        from the_table.bureau_adapter import BureauSession
        from the_table.ledger_sink import LedgerSink

        box_dir = tempfile.mkdtemp(prefix="the-table-test-gm-")
        try:
            game = BureauSession()
            sink = LedgerSink(box_dir=box_dir)
            try:
                policy = random_policy(random.Random(7))
                result = run_session(
                    game, policy, seed=7, sink=sink, max_turns=500, session_id="test-gm-integration",
                )
                self.assertTrue(game.is_terminal())
                self.assertIsInstance(result, Result)
                self.assertEqual(result.winners, [0])
                self.assertTrue(sink.verify(), sink._last_verify_output)
            finally:
                sink.close()
        finally:
            shutil.rmtree(box_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
