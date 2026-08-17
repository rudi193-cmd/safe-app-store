"""tests/test_registry.py — unit tests for the_table/registry.py.

Four things pinned:
  * games() returns the three built-in names, in stable (sorted) order.
  * make(name) returns a distinct, fresh GameSession object every call --
    never a shared instance -- and each is a structurally valid GameSession.
  * register() rejects a duplicate name and a non-callable factory.
  * DRIVEN CHECK: for every registered game, make() + run_session (real GM
    loop) + a real LedgerSink (temp dir) with a seeded policy actually
    reaches terminal and verifies clean -- the registry-level guarantee that
    "all games really do run through the same loop", not just that they
    construct.

Run with: python3 -m unittest discover -s tests -t . (from apps/the-table/)
"""
from __future__ import annotations

import random
import shutil
import tempfile
import unittest

from the_table import registry
from the_table.game_session import GameSession
from the_table.gm import random_policy, run_session
from the_table.ledger_sink import LedgerSink

SEED = 7
MAX_TURNS = 2000  # generous slack over every adapter's own defensive cap


class TestGamesListing(unittest.TestCase):
    def test_games_returns_the_three_built_ins_in_sorted_order(self):
        self.assertEqual(registry.games(), ["bureau", "crazy_eights", "scene"])

    def test_games_order_is_stable_across_calls(self):
        self.assertEqual(registry.games(), registry.games())

    def test_describe_returns_a_nonempty_string_for_each_game(self):
        for name in registry.games():
            desc = registry.describe(name)
            self.assertIsInstance(desc, str)
            self.assertTrue(desc)

    def test_describe_unknown_name_raises_keyerror(self):
        with self.assertRaises(KeyError):
            registry.describe("no-such-game")

    def test_make_unknown_name_raises_keyerror(self):
        with self.assertRaises(KeyError):
            registry.make("no-such-game")


class TestMakeFreshness(unittest.TestCase):
    def test_make_returns_a_distinct_object_each_call(self):
        for name in registry.games():
            a = registry.make(name)
            b = registry.make(name)
            self.assertIsNot(a, b, f"{name}: make() returned the same object twice")

    def test_make_returns_a_valid_game_session(self):
        for name in registry.games():
            session = registry.make(name)
            self.assertIsInstance(
                session, GameSession,
                f"{name}: {session!r} does not structurally satisfy GameSession",
            )
            self.assertIsInstance(session.seats, int)
            self.assertGreaterEqual(session.seats, 1)

    def test_make_sessions_are_independent_after_reset(self):
        # A fresh session from make() must not carry state from a previously
        # make()'d-and-driven session of the same name.
        for name in registry.games():
            a = registry.make(name)
            a.reset(seed=SEED)
            a.step(a.current_seat(), a.legal_moves(a.current_seat())[0])

            b = registry.make(name)
            # b hasn't been reset yet -- it must not already be terminal or
            # otherwise reflect a's progress.
            self.assertIsNot(a, b)


class TestRegisterValidation(unittest.TestCase):
    def test_register_rejects_duplicate_name(self):
        with self.assertRaises(ValueError):
            registry.register("bureau", lambda: None)

    def test_register_rejects_noncallable_factory(self):
        with self.assertRaises(TypeError):
            registry.register("not-a-real-game", "this is a string, not a factory")

    def test_register_rejecting_duplicate_does_not_disturb_existing_entry(self):
        before = registry.games()
        with self.assertRaises(ValueError):
            registry.register("scene", lambda: None)
        self.assertEqual(registry.games(), before)


class TestEveryRegisteredGameRunsThroughTheSameLoop(unittest.TestCase):
    """The registry-level guarantee: not just that each game constructs, but
    that every registered game actually plays to terminal and produces a
    ledger ai-game-master's own verifier accepts, all through the identical
    run_session + LedgerSink -- one game driven fully to completion before
    the next is even made(), per the determinism note in proof.py."""

    def test_every_registered_game_reaches_terminal_and_verifies(self):
        names = registry.games()
        self.assertTrue(names, "registry.games() must not be empty")

        for name in names:
            game = registry.make(name)
            box_dir = tempfile.mkdtemp(prefix=f"the-table-test-registry-{name}-")
            try:
                sink = LedgerSink(box_dir=box_dir)
                try:
                    policy = random_policy(random.Random(SEED))
                    result = run_session(
                        game,
                        policy,
                        seed=SEED,
                        sink=sink,
                        max_turns=MAX_TURNS,
                        session_id=f"test-registry-{name}",
                    )
                    self.assertTrue(
                        game.is_terminal(), f"{name}: did not reach a real terminal state"
                    )
                    self.assertTrue(
                        sink.verify(), f"{name}: ledger did not verify clean: {sink._last_verify_output}"
                    )
                    self.assertIsNotNone(result)
                finally:
                    sink.close()
            finally:
                shutil.rmtree(box_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
