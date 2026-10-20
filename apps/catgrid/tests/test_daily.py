"""The daily board: seeded by the beacon round, checkable from the round alone,
and no board at all when the beacon can't be read."""
from __future__ import annotations

import hashlib
import importlib.util
import unittest
from pathlib import Path

from catgrid import daily, soil
from catgrid.play import Game

R1 = "a" * 64  # a stand-in randomness, not a real round's
BESIDE = Path(__file__).resolve().parents[4] / "willow-bot" / "one-script" / "onescript" / "beacon.py"


def reader(randomness=R1, shift=0):
    return lambda rnd: {"round": rnd + shift, "randomness": randomness}


class TestTheRound(unittest.TestCase):
    def test_the_round_is_the_one_current_at_midnight_utc(self):
        rnd = daily.round_for("2026-10-19")
        t = daily.GENESIS + (rnd - 1) * daily.PERIOD
        self.assertLessEqual(t, 1792368000)  # 2026-10-19T00:00:00Z
        self.assertGreater(t + daily.PERIOD, 1792368000)

    def test_days_a_day_apart_are_2880_rounds_apart(self):
        self.assertEqual(daily.round_for("2026-10-20") - daily.round_for("2026-10-19"), 86400 // 30)

    def test_before_the_beacon_refuses(self):
        self.assertIsNone(daily.stamp("2019-01-01", reader())[0])

    def test_the_beacon_is_the_one_scripts(self):
        """Flatten F-14/F-16: the day's round, seed and stamp are the one
        script's beacon, not a restatement of it."""
        wb = importlib.import_module("onescript.beacon")
        self.assertEqual(Path(wb.__file__).resolve(), BESIDE.resolve())
        self.assertIs(daily.stamp, wb.day_stamp)
        self.assertIs(daily.round_for, wb.round_for)
        self.assertIs(daily.seed_of, wb.seed_u32)
        self.assertEqual((daily.CHAIN, daily.GENESIS, daily.PERIOD), (wb.CHAIN, wb.GENESIS, wb.PERIOD))
        self.assertEqual(daily.round_for("2026-10-19"), wb.round_at("2026-10-19T00:00:00Z"))


class TestTheStamp(unittest.TestCase):
    def test_the_seed_is_the_randomnesss(self):
        st, why = daily.stamp("2026-10-19", reader())
        self.assertEqual(why, "")
        self.assertEqual(st["seed"], int.from_bytes(hashlib.sha256(bytes.fromhex(R1)).digest()[:4], "big"))
        self.assertEqual(st["round"], daily.round_for("2026-10-19"))
        self.assertEqual(daily.check(st), "")

    def test_the_same_round_is_the_same_board_and_another_is_another(self):
        a = daily.board(daily.stamp("2026-10-19", reader())[0])
        b = daily.board(daily.stamp("2026-10-19", reader())[0])
        c = daily.board(daily.stamp("2026-10-19", reader("b" * 64))[0])
        self.assertEqual(a.digest(), b.digest())
        self.assertNotEqual(a.digest(), c.digest())

    def test_an_unreadable_beacon_gives_no_board_and_says_why(self):
        def down(rnd):
            raise OSError("403 Forbidden")
        st, why = daily.stamp("2026-10-19", down)
        self.assertIsNone(st)
        self.assertIn("could not be read", why)

    def test_an_answer_for_another_round_is_refused(self):
        st, why = daily.stamp("2026-10-19", reader(shift=1))
        self.assertIsNone(st)
        self.assertIn("not round", why)

    def test_no_randomness_is_refused(self):
        for bad in ("", "A" * 64, "a" * 63, None):
            self.assertIsNone(daily.stamp("2026-10-19", reader(bad))[0], bad)

    def test_bls_is_said_unchecked(self):
        st, _ = daily.stamp("2026-10-19", reader())
        self.assertIn("not checked", st["bls"])


class TestCheck(unittest.TestCase):
    def setUp(self):
        self.st = daily.stamp("2026-10-19", reader())[0]

    def test_a_ground_seed_is_refused(self):
        with self.assertRaisesRegex(ValueError, "not seeded by the beacon"):
            daily.board({**self.st, "seed": 7})

    def test_a_ground_seed_id_is_refused(self):
        self.assertIn("not seeded", daily.check({**self.st, "seed_id": "0" * 16}))

    def test_another_days_round_is_refused(self):
        self.assertIn("is not", daily.check({**self.st, "round": self.st["round"] + 1}))

    def test_bad_randomness_is_refused(self):
        self.assertIn("randomness", daily.check({**self.st, "randomness": "z" * 64}))

    def test_a_missing_field_is_refused(self):
        self.assertIn("not a daily stamp", daily.check({"day": "2026-10-19"}))


class TestTheLane(unittest.TestCase):
    def setUp(self):
        self.st = daily.stamp("2026-10-19", reader())[0]
        self.game = Game(daily.board(self.st), self.st["seed"])
        self.game.step(("hint",))

    def rec(self):
        return soil.records(self.game, self.st)[0][2]

    def test_a_daily_record_carries_its_stamp_and_replays(self):
        rec = self.rec()
        self.assertEqual(rec["daily"]["round"], self.st["round"])
        self.assertEqual(soil.replay(rec).cells, self.game.cells)

    def test_a_daily_record_with_a_ground_seed_is_refused(self):
        rec = self.rec()
        rec["daily"]["seed"] = 7
        with self.assertRaisesRegex(ValueError, "beacon round"):
            soil.replay(rec)

    def test_a_daily_stamp_on_another_seeds_record_is_refused(self):
        rec = self.rec()
        other = soil.records(Game.new(7, 6), None)[0][2]
        with self.assertRaisesRegex(ValueError, "seed differs"):
            soil.replay({**other, "daily": rec["daily"]})

    def test_a_ground_game_with_a_matching_forged_stamp_is_refused(self):
        # seed 7's board, stamped as the day's with seed 7: the seeds agree, but
        # 7 is not the round's randomness, so the stamp itself must fail
        other = soil.records(Game.new(7, 6), None)[0][2]
        forged = {**self.rec()["daily"], "seed": 7}
        with self.assertRaisesRegex(ValueError, "not seeded by the beacon"):
            soil.replay({**other, "daily": forged})

    def test_an_ordinary_record_carries_no_stamp(self):
        self.assertNotIn("daily", soil.records(Game.new(7, 6))[0][2])


if __name__ == "__main__":
    unittest.main()
