"""Gates for the baseline harness: it produces well-formed, reproducible stats.

Small N (fast); the committed numbers themselves live in baselines/baselines-N500.md
and are reproduced by running the harness, not asserted here.
"""
import unittest

from the_table import registry
from the_table.baseline import run_baseline


class TestBaseline(unittest.TestCase):
    def test_covers_every_registered_game(self):
        data = run_baseline(rounds=20)
        self.assertEqual(set(data), set(registry.games()))

    def test_each_round_has_exactly_one_outcome(self):
        # every round is either won (by one seat, or shared in a tie) or a
        # no-winner; the two must partition the rounds with none double-counted
        # or dropped, and a seat's win is credited once per round it won.
        data = run_baseline(rounds=20)
        for name, rec in data.items():
            self.assertEqual(rec["won"] + rec["no_winner"], rec["rounds"],
                             f"{name}: won+no_winner != rounds")
            credited = sum(rec["wins_by_seat"].values())
            if rec["shared"] == 0:
                self.assertEqual(credited, rec["won"], f"{name}: a win credited twice")
            else:
                self.assertGreater(credited, rec["won"], name)
                # a shared round credits at most every seat that won anything
                extra = len(rec["wins_by_seat"]) - 1
                self.assertLessEqual(credited, rec["won"] + rec["shared"] * extra, name)

    def test_turn_stats_are_ordered(self):
        data = run_baseline(rounds=20)
        for name, rec in data.items():
            t = rec["turns"]
            self.assertLessEqual(t["min"], t["median"])
            self.assertLessEqual(t["median"], t["max"])
            self.assertTrue(t["min"] <= t["mean"] <= t["max"])

    def test_scene_beats_account_for_every_beat(self):
        data = run_baseline(rounds=20)
        scene = data["scene"]
        self.assertIn("beat_status", scene)
        # a 6-beat scene, so total statuses tallied == rounds * 6
        self.assertEqual(sum(scene["beat_status"].values()), 20 * 6)
        self.assertEqual(set(scene["beat_status"]),
                         {"ARCHITECT_ROLL", "SUCCESS_STANDARD", "CHAOS_BURST"})

    def test_catgrid_endings_account_for_every_round(self):
        # each catgrid round ends solved, out of hearts, or at the cap; none twice
        data = run_baseline(rounds=20)
        for name in ("catgrid", "catgrid_2cat", "catgrid_3cat"):
            rec = data[name]
            ends = rec.get("endings", {})
            self.assertLessEqual(set(ends), {"solved", "out of hearts"}, name)
            self.assertEqual(sum(ends.values()) + rec["unresolved"], rec["rounds"], name)

    def test_reproducible(self):
        self.assertEqual(run_baseline(rounds=15), run_baseline(rounds=15))


if __name__ == "__main__":
    unittest.main()
