"""J2 (R6, R7): one seeded dice stream for every game.

Cites: SPEC.md R6/R7, SPEC-documented.md phase J2-seeded-dice (d) and C8/C9,
SPEC-rival.md section 4 and tests T8 (reseed), T9 (creator draws),
T15 (shuffle in place), T16 (generator / engine mismatch refuses replay).

The stream is the DEFAULT for SceneSession and StorySession; ``LEGACY`` is the
explicit opt-out that reproduces old recorded runs. Crazy Eights keeps
``random.Random`` by default (C8). No ``rng*`` key ever appears in a view.
"""
from __future__ import annotations

import importlib.util
import json
import os
import random
import tempfile
import threading
import time
import unittest
from pathlib import Path

from the_table import game_engine_adapter as gea
from the_table.crazy_eights_adapter import CrazyEightsSession
from the_table.dice_source import engine_hash, replay_roll, rolled_with
from the_table.game_engine_adapter import SceneSession
from the_table.gm import first_legal_policy, run_session
from the_table.ledger_sink import LedgerSink
from the_table.story_session import StorySession
from the_table.stream import (
    GENERATOR_ID,
    LEGACY,
    EngineMismatch,
    GeneratorMismatch,
    ReplayRefused,
    Stream,
    StreamRandom,
    replay,
)

_PLAY = Path(os.environ.get(
    "TABLE_PLAY_PY",
    "/home/user/sandbox/repos/willows-grove/seat/willow/experiments/predictions-2026-10-17/play.py"))
_WORLD = Path(__file__).resolve().parents[1] / "worlds" / "hasbeen.json"
SEEDS = [0, 1, 7, 42, 2**40 + 5, bytes.fromhex("ab" * 32), "ab" * 32]
ENGINE_GLOBALS = gea.Engine.roll.__globals__
_PINNED_00 = [1047558141, 719438236, 3625931128, 4276875654, 2560176255]


def factory(seed):
    return StreamRandom.from_seed(seed)


def _play_mod():
    spec = importlib.util.spec_from_file_location("_play_under_test", _PLAY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _scene_trace(seed, beats=6, **kw):
    s = SceneSession(beats=beats, **kw)
    s.reset(seed)
    out = []
    for _ in range(beats):
        o = s.step(0, ("act", "Grit"))
        out.append((o.view["last_result"], o.view["last_status"], s.last_roll.get("counter")))
    return out, s.last_roll


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


@unittest.skipUnless(_PLAY.exists(), "play.py not found (set TABLE_PLAY_PY)")
class TestStreamMatchesPlay(unittest.TestCase):
    def test_stream_output_equals_play_stream(self):
        P = _play_mod().Stream
        for seed in (b"\x00", b"abc", bytes.fromhex("cd" * 32) + b"pick"):
            a, b = Stream(seed), P(seed)
            self.assertEqual([a.u32() for _ in range(50)], [b.u32() for _ in range(50)])
            self.assertEqual(Stream(seed).shuffle(list(range(30))), P(seed).shuffle(list(range(30))))

    def test_rejection_heavy_below_matches_play(self):
        P = _play_mod().Stream
        k = 2**31 + 1  # cap = 2**31 + 1: about half of all draws are rejected
        for seed in (b"r1", b"r2", b"r3"):
            a, b = Stream(seed), P(seed)
            got = [a.below(k) for _ in range(200)]
            self.assertEqual(got, [b.below(k) for _ in range(200)])
            self.assertEqual(a.n, b.n)
            self.assertGreater(a.n, 250)  # rejections really happened
        for k in (3, 6, 52, 1, 2, 2**32 - 1, 2**32):
            a, b = Stream(b"k"), P(b"k")
            self.assertEqual([a.below(k) for _ in range(40)], [b.below(k) for _ in range(40)])

    def test_stream_matches_play_rounds(self):
        mod = _play_mod()
        n = 0
        for f in sorted((_PLAY.parent / "rounds").glob("*.json")):
            r = json.loads(f.read_text())
            if "reveal" not in r:
                continue
            seed = bytes.fromhex(r["reveal"]["beacon"]["randomness"])
            for q, want in r["reveal"]["answers"].items():
                got = bool(mod.DECK[q][1](Stream(seed + q.encode())))
                self.assertEqual(got, want, f"{f.name} {q}")
                n += 1
        self.assertGreater(n, 0)


class TestStream(unittest.TestCase):
    def test_known_vector_pinned_bytes(self):
        s = Stream(b"\x00")  # pinned: sha256(seed || n as 8 bytes big-endian)[:4], any Python
        self.assertEqual([s.u32() for _ in range(5)], _PINNED_00)
        self.assertEqual(Stream.from_seed(0).seed, b"\x00")
        self.assertEqual(Stream.from_seed(256).seed, b"\x01\x00")
        self.assertEqual(Stream.from_seed("0a0b").seed, b"\x0a\x0b")
        self.assertEqual(Stream.from_seed(5, b"pick").seed, b"\x05pick")

    def test_below_refuses_zero_negative_and_too_big(self):
        for k in (0, -3, 2**32 + 1, 2**40):
            with self.assertRaises(ValueError):
                Stream(b"x").below(k)
        r = StreamRandom.from_seed(1)
        with self.assertRaises(ValueError):
            r.randint(0, 2**32)  # 2**32 + 1 values
        self.assertIn(r.randint(0, 2**32 - 1), range(2**32))

    def test_below_has_no_modulo_bias_at_large_k(self):
        k = 2**31 + 1  # a plain modulo would put twice the mass on the low residues
        s = Stream(b"bias")
        n = 30000
        low = sum(1 for _ in range(n) if s.below(k) < k // 2)
        # fair: p = (k//2)/k ~ 0.5 ; sd = sqrt(n/4) ~ 87 ; 5 sigma bound
        self.assertLess(abs(low - n / 2), 5 * (n / 4) ** 0.5)
        # chi-square on 3 buckets at k = 3, N = 30000 (df = 2, 0.001 point 13.8)
        s = Stream(b"bias3")
        counts = [0, 0, 0]
        for _ in range(n):
            counts[s.below(3)] += 1
        chi = sum((c - n / 3) ** 2 / (n / 3) for c in counts)
        self.assertLess(chi, 13.8)


class TestShim(unittest.TestCase):
    def test_shuffle_in_place_matches_copy(self):  # T15
        for seed in (b"a", b"b"):
            xs = list(range(40))
            r = StreamRandom(Stream(seed))
            self.assertIsNone(r.shuffle(xs))
            self.assertEqual(xs, Stream(seed).shuffle(list(range(40))))
            self.assertGreaterEqual(r.counter, len(xs) - 1)

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


class TestDefaultIsTheStream(unittest.TestCase):
    def test_global_random_untouched_on_a_default_story(self):
        random.seed(123)
        before = random.getstate()
        s = StorySession(_WORLD)  # DEFAULT: no factory
        s.reset(5)
        _drive_story(s)
        self.assertEqual(random.getstate(), before)
        self.assertEqual(s.last_roll["generator_id"], GENERATOR_ID)
        _scene_trace(5)
        self.assertEqual(random.getstate(), before)

    def test_default_scene_replays_and_matches_explicit_stream(self):
        for seed in SEEDS:
            self.assertEqual(_scene_trace(seed), _scene_trace(seed))
        self.assertEqual(_scene_trace(3), _scene_trace(3, rng_factory=factory))

    def test_interleaved_default_scenes_are_each_deterministic(self):  # T8
        solo = {sd: _scene_trace(sd)[0] for sd in (11, 12)}
        a, b = SceneSession(), SceneSession()
        a.reset(11)
        b.reset(12)
        ta, tb = [], []
        for _ in range(6):
            oa = a.step(0, ("act", "Grit"))
            ob = b.step(0, ("act", "Grit"))
            ta.append((oa.view["last_result"], oa.view["last_status"], a.last_roll["counter"]))
            tb.append((ob.view["last_result"], ob.view["last_status"], b.last_roll["counter"]))
        self.assertEqual(ta, solo[11])
        self.assertEqual(tb, solo[12])

    def test_no_view_ever_carries_rng_keys(self):
        def keys(v):
            return [k for k in v if k.startswith("rng")]
        s = SceneSession()
        self.assertEqual(keys(s.reset(1).view) + keys(s.step(0, ("act", "Grit")).view), [])
        st = StorySession(_WORLD)
        self.assertEqual(keys(st.reset(1).view), [])
        for views in (_drive_story(st),):
            self.assertTrue(all(not keys(v) for v in views))
        for fac in (None, factory):
            c = CrazyEightsSession(rng_factory=fac)
            self.assertEqual(keys(c.reset(2).view), [])
            self.assertEqual(keys(c.observe(1).view), [])

    def test_story_rows_carry_the_record_but_not_the_seed(self):
        def run(seed):
            s = StorySession(_WORLD)
            s.reset(seed)
            return _drive_story(s), s.last_roll
        (v1, r1), (v2, r2) = run(77), run(77)
        self.assertEqual((v1, r1), (v2, r2))
        self.assertEqual(
            set(r1), {"seed_id", "generator_id", "counter", "counter_before",
                      "stat", "result", "status", "stat_value", "engine_hash"})
        self.assertEqual(r1["engine_hash"], engine_hash())
        self.assertGreater(r1["counter"], r1["counter_before"])
        self.assertNotIn(Stream.from_seed(77).seed.hex(), json.dumps(r1))
        self.assertTrue(any(run(sd)[1]['result'] != r1['result'] for sd in range(78, 90)))

    def test_ledger_rows_carry_the_roll_record(self):
        with tempfile.TemporaryDirectory() as box:
            sink = LedgerSink(box_dir=box)
            run_session(SceneSession(beats=3), first_legal_policy(), seed=4, sink=sink)
            rows = sink._con.execute("SELECT state FROM ledger WHERE kind='turn'").fetchall()
            sink.close()
        recs = [json.loads(r[0])["roll"] for r in rows]
        self.assertEqual(len(recs), 3)
        self.assertTrue(all(r["generator_id"] == GENERATOR_ID and "seed_id" in r for r in recs))
        self.assertEqual([r["counter_before"] for r in recs[1:]], [r["counter"] for r in recs[:-1]])


class TestResetNarration(unittest.TestCase):
    def test_reset_narrates_seed_id_not_the_seed(self):
        hexseed = "ab" * 32
        for obs in (SceneSession().reset(hexseed), StorySession(_WORLD).reset(hexseed),
                    CrazyEightsSession(rng_factory=factory).reset(hexseed)):
            text = " ".join(obs.narration)
            self.assertNotIn(hexseed, text)
            self.assertIn("seed_id=" + StreamRandom.from_seed(hexseed).seed_id, text)

    def test_legacy_narration_unchanged(self):
        self.assertIn("(seed=5)", SceneSession(rng_factory=LEGACY).reset(5).narration[0])
        self.assertIn("(seed=5)", StorySession(_WORLD, rng_factory=LEGACY).reset(5).narration[0])
        self.assertIn("(seed=5)", CrazyEightsSession().reset(5).narration[0])


class TestLegacyOptOut(unittest.TestCase):
    """C9: an old recorded run is still reproducible, under its own name."""

    def test_legacy_scene_reproduces_the_recorded_runs(self):
        pinned = {0: [10, 6, 10, 8, 8, 8], 5: [10, 11, 14, 13, 7, 10], 42: [9, 9, 7, 6, 8, 13]}
        for seed, want in pinned.items():
            s = SceneSession(rng_factory=LEGACY)
            s.reset(seed)
            got = [s.step(0, ("act", "Grit")).view["last_result"] for _ in range(6)]
            self.assertEqual(got, want)
            self.assertEqual(s.last_roll["generator_id"], "random/global")

    def test_legacy_story_reproduces_the_recorded_run_and_names_itself(self):
        s = StorySession(_WORLD, rng_factory=LEGACY)
        s.reset(7)
        _drive_story(s)
        self.assertEqual(
            s.result().summary,
            "Hasbeen — Late Shift: 2 beat(s) resolved (1 strong, 1 weak, 0 miss); "
            "1 decision(s) sealed [s1::b3 SEALED by Rudi]. The night held together.")
        self.assertEqual(s.last_roll["generator_id"], "random/global")

    def test_legacy_does_seed_the_global(self):
        SceneSession(rng_factory=LEGACY).reset(5)
        a = random.random()
        SceneSession(rng_factory=LEGACY).reset(5)
        self.assertEqual(a, random.random())

    def test_plain_random_random_factory_works_and_is_named(self):
        s = SceneSession(rng_factory=random.Random)
        s.reset(3)
        s.step(0, ("act", "Grit"))
        self.assertEqual(s.last_roll["generator_id"], "random/Random")
        self.assertNotIn("counter", s.last_roll)
        self.assertEqual(_scene_trace(3, rng_factory=random.Random),
                         _scene_trace(3, rng_factory=random.Random))


class TestReplay(unittest.TestCase):
    def _rec(self, seed=31337):
        s = SceneSession()
        s.reset(seed)
        s.step(0, ("act", "Cool"))
        return dict(s.last_roll)

    def test_roll_record_replays_and_reverifies_the_values(self):
        rec = self._rec()
        sheet = {"Efficiency": 2}  # the sheet a fresh scene gives "Cool"
        rng = replay_roll(31337, rec, sheet)
        self.assertEqual(rng.counter, rec["counter"])
        with self.assertRaises(ReplayRefused):
            replay_roll(31337, dict(rec, result=rec["result"] + 1), sheet)
        with self.assertRaises(ReplayRefused):  # a wrong sheet gives a different result
            replay_roll(31337, rec, {"Efficiency": 9})

    def test_replay_refuses_an_unbound_stat_value(self):
        rec = self._rec()
        with self.assertRaises(ReplayRefused):
            replay_roll(31337, rec)
        replay_roll(31337, rec, unbound_stat_ok=True)
        with self.assertRaises(ReplayRefused):  # a lied stat_value is caught by the result
            replay_roll(31337, dict(rec, stat_value=rec["stat_value"] + 3), unbound_stat_ok=True)

    def test_mismatched_generator_refuses_replay(self):  # T16
        rec = self._rec()
        with self.assertRaises(GeneratorMismatch) as cm:
            replay(31337, dict(rec, generator_id="sha256-stream/v0"))
        self.assertIn("sha256-stream/v0", str(cm.exception))
        with self.assertRaises(GeneratorMismatch):
            replay(5, rec)  # wrong seed
        with self.assertRaises(GeneratorMismatch):
            replay_roll(31337, dict(rec, generator_id="random/global"))

    def test_engine_hash_mismatch_refuses_naming_the_hash(self):  # T16
        rec = self._rec()
        with self.assertRaises(EngineMismatch) as cm:
            replay_roll(31337, dict(rec, engine_hash="0" * 64))
        self.assertIn("0" * 64, str(cm.exception))
        self.assertIn(engine_hash(), str(cm.exception))

    def test_replay_validates_the_counter_and_requires_seed_id(self):
        rec = self._rec()
        for bad in (dict(rec, counter=-1), dict(rec, counter_before=-1),
                    dict(rec, counter_before=rec["counter"] + 1),
                    dict(rec, counter="3"), dict(rec, counter=True),
                    dict(rec, counter_before=None)):
            with self.assertRaises(ReplayRefused, msg=repr(bad)):
                replay(31337, bad)
        no_id = dict(rec)
        del no_id["seed_id"]
        with self.assertRaises(ReplayRefused):
            replay(31337, no_id)
        replay(31337, rec)

    def test_creator_rolls_still_consume_two_draws(self):  # T9, engine_v1_7.py:57-58
        r = StreamRandom.from_seed(3)
        eng = gea.Engine()
        with rolled_with(r, eng):
            eng.roll("Grit", is_creator=True)
        two = Stream.from_seed(3)
        two.below(6)
        two.below(6)
        self.assertEqual(r.counter, two.n)


class TestSwapSafety(unittest.TestCase):
    def tearDown(self):
        ENGINE_GLOBALS["random"] = random

    def test_engine_random_restored_after_raise(self):
        self.assertIs(ENGINE_GLOBALS["random"], random)

        class Boom(StreamRandom):
            def randint(self, a, b):
                raise RuntimeError("boom")

        with self.assertRaises(RuntimeError):  # noqa: SIM117
            with rolled_with(Boom(Stream(b"x")), gea.Engine()):
                gea.Engine().roll("Grit")
        self.assertIs(ENGINE_GLOBALS["random"], random)
        s = SceneSession(rng_factory=lambda _s: Boom(Stream(b"x")))
        s.reset(1)
        with self.assertRaises(RuntimeError):
            s.step(0, ("act", "Grit"))
        self.assertIs(ENGINE_GLOBALS["random"], random)

    def test_nested_lifo_restores(self):
        with rolled_with(StreamRandom.from_seed(4)):  # noqa: SIM117
            with rolled_with(StreamRandom.from_seed(5)):
                pass
        self.assertIs(ENGINE_GLOBALS["random"], random)

    def test_roll_error_is_not_masked_by_a_swap_mismatch(self):  # X2
        class Meddler(StreamRandom):
            def randint(self, a, b):
                ENGINE_GLOBALS["random"] = random  # someone else writes the name
                raise KeyError("the roll's own error")

        with self.assertRaises(KeyError) as cm:  # noqa: SIM117
            with rolled_with(Meddler(Stream(b"m")), gea.Engine()) as r:
                r.randint(1, 6)
        self.assertIsInstance(cm.exception.swap_mismatch, RuntimeError)
        self.assertIn("changed under rolled_with", "".join(cm.exception.__notes__))
        self.assertIs(ENGINE_GLOBALS["random"], random)

    def test_non_lifo_exit_raises_and_nothing_leaks(self):
        a, b = rolled_with(StreamRandom.from_seed(1)), rolled_with(StreamRandom.from_seed(2))
        a.__enter__()
        b.__enter__()
        with self.assertRaises(RuntimeError):
            a.__exit__(None, None, None)
        b.__exit__(None, None, None)  # outermost exit: back to what was found
        self.assertIs(ENGINE_GLOBALS["random"], random)

    def test_threads_cannot_leak_or_cross_streams(self):
        class Slow(StreamRandom):
            def randint(self, x, y):
                time.sleep(0.003)
                return super().randint(x, y)

        solo = {i: _scene_trace(i)[0] for i in range(4)}
        got = {}

        def run(i):
            s = SceneSession(rng_factory=lambda sd: Slow(StreamRandom.from_seed(sd).stream))
            s.reset(i)
            got[i] = [(s.step(0, ("act", "Grit")).view["last_result"],) for _ in range(6)]

        ts = [threading.Thread(target=run, args=(i,)) for i in range(4)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertIs(ENGINE_GLOBALS["random"], random)
        for i in range(4):
            self.assertEqual([g[0] for g in got[i]], [t[0] for t in solo[i]])

    def test_state_file_still_untouched(self):
        p = Path(gea.__file__).resolve().parents[2] / "game" / "engine_state.json"
        before = (p.exists(), p.read_bytes() if p.exists() else None)
        _scene_trace(2)
        self.assertEqual((p.exists(), p.read_bytes() if p.exists() else None), before)


class TestLedgerRollRows(unittest.TestCase):  # X3
    def test_crazy_eights_deal_is_recorded_once_not_per_turn(self):
        with tempfile.TemporaryDirectory() as box:
            sink = LedgerSink(box_dir=box)
            run_session(CrazyEightsSession(rng_factory=factory), first_legal_policy(),
                        seed=2, sink=sink)
            ok = sink.verify()
            rows = [(k, json.loads(s)) for k, s in
                    sink._con.execute("SELECT kind, state FROM ledger ORDER BY id")]
            sink.close()
        self.assertTrue(ok)
        self.assertEqual(rows[0][0], "session_open")
        self.assertEqual(rows[0][1]["roll"]["generator_id"], GENERATOR_ID)
        self.assertTrue(all("roll" not in s for k, s in rows if k == "turn"))

    def test_scene_rows_carry_a_roll_every_turn_even_when_values_repeat(self):
        with tempfile.TemporaryDirectory() as box:
            sink = LedgerSink(box_dir=box)
            run_session(SceneSession(beats=6, rng_factory=LEGACY), first_legal_policy(),
                        seed=0, sink=sink)
            ok = sink.verify()
            turns = [json.loads(s) for (s,) in
                     sink._con.execute("SELECT state FROM ledger WHERE kind='turn'")]
            sink.close()
        self.assertTrue(ok)
        self.assertTrue(all(t["roll"]["generator_id"] == "random/global" for t in turns))
        self.assertEqual(len(turns), 6)


class TestEngineHash(unittest.TestCase):  # X4
    def test_hash_follows_the_source_file(self):
        import hashlib
        path = ENGINE_GLOBALS["__file__"]
        self.assertEqual(engine_hash(), hashlib.sha256(Path(path).read_bytes()).hexdigest())


class TestCrazyEights(unittest.TestCase):
    def test_default_is_random_random_unchanged(self):  # C8
        from crazy_eights import make_deck  # on sys.path once the adapter is imported
        legacy = CrazyEightsSession()
        view = legacy.reset(8).view
        d = random.Random(8)
        deck = make_deck()
        d.shuffle(deck)
        self.assertEqual(view["hand"], [list(c) for c in deck[:5]])
        self.assertEqual(legacy.last_roll["generator_id"], "random/Random")

    def test_stream_deal_replays(self):
        a, b = CrazyEightsSession(rng_factory=factory), CrazyEightsSession(rng_factory=factory)
        self.assertEqual(a.reset(8).view, b.reset(8).view)
        self.assertEqual(a.last_roll["generator_id"], GENERATOR_ID)
        self.assertNotEqual(a.reset(8).view["hand"], CrazyEightsSession().reset(8).view["hand"])
        r = run_session(CrazyEightsSession(rng_factory=factory), first_legal_policy(), seed=2)
        r2 = run_session(CrazyEightsSession(rng_factory=factory), first_legal_policy(), seed=2)
        self.assertEqual(r, r2)


if __name__ == "__main__":
    unittest.main()


class TestDice5eKeepFormsOnTheStream(unittest.TestCase):
    """W4 break 6 / T15 (R6 limit): the `dice` library's keep operators ignore
    an injected random; dice5e rolls AdBhK / AdBlK itself, on the stream, and
    refuses a library roll that touches the global random under a stream."""

    def test_keep_forms_never_touch_global_random(self):
        from aetheris5e import dice5e
        seed = "ab" * 32
        got = []
        for g in (0, 1):
            random.seed(g)
            before = random.getstate()
            got.append([dice5e.total(e, StreamRandom.from_seed(seed))
                        for e in ("6d6l4", "4d6h3", "2d20h1", "2d20l1")])
            self.assertEqual(random.getstate(), before)
        self.assertEqual(got[0], got[1])

    def test_a_library_keep_form_under_a_stream_is_refused_and_put_back(self):
        from aetheris5e import dice5e
        random.seed(3)
        before = random.getstate()
        with self.assertRaisesRegex(dice5e.GlobalRandomUsed, "R6 limit"):
            dice5e.total("4d6l3+1", StreamRandom.from_seed("cd" * 32))
        self.assertEqual(random.getstate(), before)
        # the global module itself, handed in, is the caller's own choice
        self.assertTrue(4 <= dice5e.total("4d6l3+1", random) <= 19)
