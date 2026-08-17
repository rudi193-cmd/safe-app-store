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
        # every round is either won by exactly one seat or a no-winner; the two
        # must partition the rounds with none double-counted or dropped.
        data = run_baseline(rounds=20)
        for name, rec in data.items():
            won = sum(rec["wins_by_seat"].values())
            self.assertEqual(won + rec["no_winner"], rec["rounds"],
                             f"{name}: wins+no_winner != rounds")

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

    def test_reproducible(self):
        self.assertEqual(run_baseline(rounds=15), run_baseline(rounds=15))


if __name__ == "__main__":
    unittest.main()
