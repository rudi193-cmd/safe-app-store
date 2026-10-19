"""pools.py: every round lands in exactly one pool, pools are banded the way
peaks bands a forecast, competent policies only ever play legal moves from a
seat's own view, and the same N gives the same numbers.

Run with: python3 -m unittest discover -s tests -t . (from apps/the-table/)
"""
from __future__ import annotations

import random
import unittest
from unittest import mock

from the_table import pools, registry
from the_table.game_session import Result

QUICK = [g for g in registry.games() if g != "catgrid_3cat"]


class TestPools(unittest.TestCase):
    def test_every_round_lands_in_exactly_one_pool(self):
        for name in QUICK:
            m = pools.measure(name, "random", 6)
            self.assertEqual(sum(p["n"] for p in m["pools"]), 6, name)
            self.assertEqual(sum(b["n"] for b in m["lengths"]["hist"]), 6, name)

    def test_bands_are_peaks_bands(self):
        m = pools.measure("crazy_eights", "random", 40)
        top = max(p["n"] for p in m["pools"])
        for p in m["pools"]:
            want = ("likely" if p["n"] == top else
                    "middle" if p["n"] / 40 >= float(pools.MIDDLE_FLOOR) else "outlier")
            self.assertEqual(p["band"], want, p)

    def test_the_same_n_gives_the_same_numbers(self):
        self.assertEqual(pools.measure("liars_dice", "john", 5), pools.measure("liars_dice", "john", 5))

    def test_a_cut_off_round_is_its_own_pool_and_counted(self):
        with mock.patch.object(pools, "CAP", 3):
            m = pools.measure("checkers", "random", 4)
        self.assertEqual(m["cap_hits"], 4)
        self.assertEqual(m["pools"], [{"ending": "cut off by the cap", "n": 4, "p": 1.0, "band": "likely"}])


class TestCompetentPoliciesPlayFair(unittest.TestCase):
    def test_every_john_move_is_legal_from_the_seats_own_view(self):
        for name in pools.JOHN:
            if name == "catgrid_3cat":
                continue
            for seed in range(3):
                game, rng = registry.make(name), random.Random(seed)
                game.reset(seed)
                for _ in range(400):
                    if game.is_terminal():
                        break
                    seat = game.current_seat()
                    legal = [list(m) for m in game.legal_moves(seat)]
                    move = pools.JOHN[name](game.observe(seat).view, game.legal_moves(seat), rng)
                    self.assertIn(list(move), legal, (name, seed, move))
                    game.step(seat, move)

    def test_johns_choices_are_game_labs(self):
        from hearts import choose_pass_john
        from liars_dice import john_action

        game = registry.make("hearts")
        game.reset(4)
        view = game.observe(0).view
        move = pools.JOHN["hearts"](view, game.legal_moves(0), random.Random(0))
        self.assertEqual(sorted(tuple(c) for c in move[1:]),
                         sorted(choose_pass_john([tuple(c) for c in view["hand"]])))
        game = registry.make("liars_dice")
        game.reset(4)
        seat = game.current_seat()
        view = game.observe(seat).view
        kind, bid = john_action(None, view["my_dice"], sum(view["dice_left"]))
        self.assertEqual(pools.JOHN["liars_dice"](view, game.legal_moves(seat), random.Random(0)),
                         ("bid", *bid))

    def test_games_without_one_are_said(self):
        with mock.patch.object(pools, "measure", lambda name, policy, n: {"policy": policy}):
            data = pools.run(1)
        for name, g in data["games"].items():
            if name in pools.JOHN:
                self.assertIn("john", g["policies"])
            else:
                self.assertEqual(list(g["policies"]), ["random"])
                self.assertIn("random only", g["no_competent_policy"])


class TestReads(unittest.TestCase):
    def test_a_tied_lead_is_no_leader(self):
        self.assertIsNone(pools.leader("checkers", {"material": [12, 12]}))
        self.assertEqual(pools.leader("checkers", {"material": [12, 11]}), 0)
        self.assertIsNone(pools.leader("liars_dice", {"dice_left": [5, 5, 3, 0]}))
        self.assertEqual(pools.leader("hearts", {"phase": "play", "points": [3, 0, 5, 9]}), 1)
        self.assertIsNone(pools.leader("hearts", {"phase": "pass", "points": [0, 0, 0, 0]}))

    def test_backgammon_lower_pips_lead(self):
        v = {"seat": 1, "me": {"pips": 100}, "them": {"pips": 120}}
        self.assertEqual(pools.leader("backgammon", v), 1)

    def test_hearts_moon_and_shares(self):
        moon = Result(winners=[2], scores={0: 26.0, 1: 26.0, 2: 0.0, 3: 26.0}, summary="")
        self.assertEqual(pools.ending("hearts", moon, True), "shot the moon")
        two = Result(winners=[0, 1], scores={0: 3.0, 1: 3.0, 2: 10.0, 3: 10.0}, summary="")
        self.assertEqual(pools.ending("hearts", two, True), "2 share the lowest")

    def test_catgrid_keeps_its_hearts(self):
        r = Result(winners=[0], scores={0: 2.0}, summary="solved with 2 heart(s) left")
        self.assertEqual(pools.ending("catgrid", r, True), "solved with 2 heart(s) left")


if __name__ == "__main__":
    unittest.main()
