"""J2 (R6, R7): one seeded dice stream for every game.

Cites: SPEC.md R6/R7, SPEC-documented.md phase J2-seeded-dice (d), SPEC-rival.md
section 4 / tests T8 (reseed), T9 (creator draws), T15 (shuffle in place),
T16 (generator mismatch refuses replay).
"""
from __future__ import annotations

import importlib.util
import json
import random
import unittest
from pathlib import Path

from crazy_eights import make_deck  # on sys.path via the adapter shim

from the_table import game_engine_adapter as gea
from the_table.crazy_eights_adapter import CrazyEightsSession
from the_table.dice_source import rolled_with
from the_table.game_engine_adapter import SceneSession
from the_table.gm import first_legal_policy, run_session
from the_table.story_session import StorySession
from the_table.stream import (
    GENERATOR_ID,
    GeneratorMismatch,
    Stream,
    StreamRandom,
    replay,
)

_PLAY = Path("/home/user/willows-grove/seat/willow/experiments/predictions-2026-10-17/play.py")
_WORLD = Path(__file__).resolve().parents[1] / "worlds" / "hasbeen.json"
SEEDS = [0, 1, 7, 42, 2**40 + 5, bytes.fromhex("ab" * 32), "ab" * 32]


def factory(seed):
    return StreamRandom.from_seed(seed)


def _play_stream():
    spec = importlib.util.spec_from_file_location("_play_under_test", _PLAY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.Stream


def _scene_trace(seed, beats=6):
    s = SceneSession(beats=beats, rng_factory=factory)
    s.reset(seed)
    out = []
    for _ in range(beats):
        o = s.step(0, ("act", "Grit"))
        out.append((o.view["last_result"], o.view["last_status"], o.view["rng_counter"]))
    return out, s.last_roll


class TestStreamMatchesPlay(unittest.TestCase):
    @unittest.skipUnless(_PLAY.exists(), "play.py not beside this checkout")
    def test_stream_output_equals_play_stream(self):
        P = _play_stream()
        for seed in (b"\x00", b"abc", bytes.fromhex("cd" * 32) + b"pick"):
            a, b = Stream(seed), P(seed)
            self.assertEqual([a.u32() for _ in range(50)], [b.u32() for _ in range(50)])
            a, b = Stream(seed), P(seed)
            self.assertEqual([a.below(k) for k in (3, 6, 52, 1, 2) * 20],
                             [b.below(k) for k in (3, 6, 52, 1, 2) * 20])
            self.assertEqual(Stream(seed).shuffle(list(range(30))), P(seed).shuffle(list(range(30))))

    def test_known_vector(self):
        s = Stream(b"\x00")
        first = [s.u32() for _ in range(3)]
        self.assertEqual(first, [Stream(b"\x00").u32()] + first[1:])  # deterministic
        self.assertEqual(Stream.from_seed(0).seed, b"\x00")
        self.assertEqual(Stream.from_seed(256).seed, b"\x01\x00")
        self.assertEqual(Stream.from_seed("0a0b").seed, b"\x0a\x0b")
        self.assertEqual(Stream.from_seed(5, b"pick").seed, b"\x05pick")

    def test_below_refuses_zero_and_negative(self):
        for k in (0, -3):
            with self.assertRaises(ValueError):
                Stream(b"x").below(k)


class TestShim(unittest.TestCase):
    def test_shuffle_in_place_matches_copy(self):  # T15
        for seed in (b"a", b"b"):
            xs = list(range(40))
            r = StreamRandom(Stream(seed))
            self.assertIsNone(r.shuffle(xs))
            self.assertEqual(xs, Stream(seed).shuffle(list(range(40))))
            self.assertGreaterEqual(r.counter, len(xs) - 1)  # one draw per swap, rejections add more

    def test_randint_choice_random(self):
        r = StreamRandom(Stream(b"k"))
        for _ in range(200):
            self.assertIn(r.randint(1, 6), range(1, 7))
        self.assertEqual(r.randint(4, 4), 4)
        self.assertIn(r.choice("abc"), "abc")
        self.assertTrue(0.0 <= r.random() < 1.0)
        with self.assertRaises(IndexError):
            r.choice([])
        with self.assertRaises(ValueError):
            r.randint(3, 2)
        self.assertEqual(r.generator_id, GENERATOR_ID)

    def test_dice_library_and_dice5e_accept_it(self):
        import dice

        from aetheris5e import dice5e
        a = dice.roll("3d6", random=StreamRandom.from_seed(9))
        b = dice.roll("3d6", random=StreamRandom.from_seed(9))
        self.assertEqual(list(a), list(b))
        self.assertEqual(dice5e.total("2d20+3", StreamRandom.from_seed(9)),
                         dice5e.total("2d20+3", StreamRandom.from_seed(9)))


class TestEngineSeam(unittest.TestCase):
    def test_replay_identical(self):
        for seed in SEEDS:
            self.assertEqual(_scene_trace(seed), _scene_trace(seed))

    def test_interleaved_scenes_are_each_deterministic(self):  # T8
        solo = {sd: _scene_trace(sd) for sd in (11, 12)}
        a, b = SceneSession(rng_factory=factory), SceneSession(rng_factory=factory)
        a.reset(11); b.reset(12)
        ta, tb = [], []
        for _ in range(6):
            oa = a.step(0, ("act", "Grit")); ob = b.step(0, ("act", "Grit"))
            ta.append((oa.view["last_result"], oa.view["last_status"], oa.view["rng_counter"]))
            tb.append((ob.view["last_result"], ob.view["last_status"], ob.view["rng_counter"]))
        self.assertEqual(ta, solo[11][0])
        self.assertEqual(tb, solo[12][0])

    def test_stream_leaves_global_random_alone(self):
        random.seed(123)
        before = random.getstate()
        _scene_trace(5)
        s = StorySession(_WORLD, rng_factory=factory)
        s.reset(5)
        self.assertEqual(random.getstate(), before)
        _drive_story(s)
        self.assertEqual(random.getstate(), before)

    def test_story_replays_and_rows_carry_the_record(self):
        def run(seed):
            s = StorySession(_WORLD, rng_factory=factory)
            s.reset(seed)
            views = _drive_story(s)
            return views, s.last_roll
        v1, r1 = run(77)
        v2, r2 = run(77)
        self.assertEqual(v1, v2)
        self.assertEqual(r1, r2)
        self.assertEqual(r1["generator_id"], GENERATOR_ID)
        self.assertEqual(set(r1), {"seed_id", "generator_id", "counter", "counter_before"})
        self.assertGreater(r1["counter"], r1["counter_before"])
        self.assertTrue(all(v["rng"] == GENERATOR_ID for v in v1))
        self.assertNotEqual(run(78)[0], v1)

    def test_roll_record_replays_the_roll(self):
        s = SceneSession(rng_factory=factory)
        s.reset(31337)
        o = s.step(0, ("act", "Cool"))
        rec = s.last_roll
        rng = replay(31337, rec)
        self.assertEqual(rng.counter, rec["counter_before"])
        # redo the same roll from the recorded position on a fresh scene
        fresh = SceneSession(rng_factory=lambda _s: replay(31337, rec))
        fresh.reset(31337)
        o2 = fresh.step(0, ("act", "Cool"))
        self.assertEqual(o.view["last_result"], o2.view["last_result"])

    def test_creator_rolls_still_consume_two_draws(self):  # T9, engine_v1_7.py:57-58
        r = StreamRandom.from_seed(3)
        eng = gea.Engine()
        with rolled_with(r):
            eng.roll("Grit", is_creator=True)
        two = Stream.from_seed(3)
        two.below(6); two.below(6)
        self.assertEqual(r.counter, two.n)

    def test_mismatched_generator_refuses_replay(self):  # T16
        s = SceneSession(rng_factory=factory)
        s.reset(4)
        s.step(0, ("act", "Grit"))
        rec = dict(s.last_roll, generator_id="sha256-stream/v0")
        with self.assertRaises(GeneratorMismatch) as cm:
            replay(4, rec)
        self.assertIn("sha256-stream/v0", str(cm.exception))
        with self.assertRaises(GeneratorMismatch):
            replay(5, s.last_roll)  # wrong seed

    def test_engine_random_restored_after_raise(self):
        mod = gea.Engine.roll.__globals__
        self.assertIs(mod["random"], random)

        class Boom(StreamRandom):
            def randint(self, a, b):
                raise RuntimeError("boom")

        with self.assertRaises(RuntimeError), rolled_with(Boom(Stream(b"x"))):
            gea.Engine().roll("Grit")
        self.assertIs(mod["random"], random)
        s = SceneSession(rng_factory=lambda _s: Boom(Stream(b"x")))
        s.reset(1)
        with self.assertRaises(RuntimeError):
            s.step(0, ("act", "Grit"))
        self.assertIs(mod["random"], random)

    def test_default_sessions_unchanged(self):
        s = SceneSession(); o = s.reset(9); o = s.step(0, ("act", "Grit"))
        self.assertNotIn("rng", o.view)
        self.assertIsNone(s.last_roll)
        c = CrazyEightsSession(); self.assertNotIn("rng", c.reset(9).view)

    def test_state_file_still_untouched(self):
        p = Path(gea.__file__).resolve().parents[2] / "game" / "engine_state.json"
        before = (p.exists(), p.read_bytes() if p.exists() else None)
        _scene_trace(2)
        self.assertEqual((p.exists(), p.read_bytes() if p.exists() else None), before)


class TestCrazyEights(unittest.TestCase):
    def test_stream_deal_replays_and_default_is_unchanged(self):
        a = CrazyEightsSession(rng_factory=factory); b = CrazyEightsSession(rng_factory=factory)
        va, vb = a.reset(8).view, b.reset(8).view
        self.assertEqual(va, vb)
        self.assertEqual(va["rng"], GENERATOR_ID)
        d = random.Random(8)
        deck = make_deck()
        d.shuffle(deck)
        legacy = CrazyEightsSession().reset(8).view
        self.assertEqual(legacy["hand"], [list(c) for c in deck[:5]])
        self.assertNotEqual(legacy["hand"], va["hand"])

    def test_full_game_with_stream(self):
        r = run_session(CrazyEightsSession(rng_factory=factory), first_legal_policy(), seed=2)
        r2 = run_session(CrazyEightsSession(rng_factory=factory), first_legal_policy(), seed=2)
        self.assertEqual(r, r2)


def _drive_story(s):
    views = []
    while not s.is_terminal():
        p = s.pending_seal()
        if p is not None:
            s.seal(p["fact_id"], by="Rudi")
            continue
        seat = s.current_seat()
        o = s.step(seat, s.legal_moves(seat)[0])
        views.append(json.loads(json.dumps(o.view)))
    return views


if __name__ == "__main__":
    unittest.main()
