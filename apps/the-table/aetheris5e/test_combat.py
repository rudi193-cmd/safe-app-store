"""test_combat.py -- lock the Aetheris 5e combat engine's behavior, including
the forbidden acts (a tampered combat log must REFUSE to verify; a dead
combatant must not act).

Run from apps/the-table/aetheris5e/:
    python3 -m unittest test_combat -v
"""
from __future__ import annotations

import os
import random
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

import combat  # noqa: E402
import dice5e  # noqa: E402
import statblocks  # noqa: E402
import dice as _dicelib  # noqa: E402
from the_table.ledger_sink import LedgerSink  # noqa: E402


def _lib_total(expr, rng):
    v = _dicelib.roll(expr, random=rng)
    return int(v) if isinstance(v, int) else sum(int(x) for x in v)


class TestDiceSeam(unittest.TestCase):
    """The cache + fast path must never diverge from the `dice` library it
    delegates to, and the library must stay the validator and the fallback."""

    def test_bounds_and_determinism(self):
        for _ in range(300):
            self.assertTrue(5 <= dice5e.total("2d6+3", random.Random(_)) <= 15)
            self.assertTrue(1 <= dice5e.total("1d20", random.Random(_)) <= 20)
        self.assertEqual(dice5e.total("3d8+2", random.Random(5)),
                         dice5e.total("3d8+2", random.Random(5)))

    def test_advantage_skews_high_disadvantage_low(self):
        import statistics as st
        adv = [dice5e.total("2d20h1", random.Random(i)) for i in range(400)]
        dis = [dice5e.total("2d20l1", random.Random(i)) for i in range(400)]
        self.assertGreater(st.mean(adv), 12.5)   # ~13.8
        self.assertLess(st.mean(dis), 8.5)       # ~7.2

    def test_fastpath_distribution_matches_library(self):
        import statistics as st
        for expr in ("4d6", "2d6+3", "1d20"):
            fast = [dice5e.total(expr, random.Random(i)) for i in range(400)]
            lib = [_lib_total(expr, random.Random(i)) for i in range(400)]
            self.assertEqual((min(fast), max(fast)), (min(lib), max(lib)),
                             f"{expr}: fast-path bounds differ from library")
            self.assertAlmostEqual(st.mean(fast), st.mean(lib), delta=0.6,
                                   msg=f"{expr}: fast-path mean drifts from library")

    def test_complex_expression_falls_back_to_library(self):
        # '1d4+1d4' is valid `dice` notation but NOT a fast-path form -> the
        # library owns it. It must still roll in-range via the seam.
        for _ in range(50):
            self.assertTrue(2 <= dice5e.total("1d4+1d4", random.Random(_)) <= 8)

    def test_library_is_the_gatekeeper_for_illegal_notation(self):
        # The `dice` library validates every expression at compile time, so
        # illegal notation is refused by it — the grammar is never ours.
        for bad in ("1d6+", "xd6", "1d"):
            with self.subTest(bad=bad), self.assertRaises(Exception):
                dice5e.total(bad, random.Random(0))

    def test_expression_is_compiled_and_cached(self):
        dice5e.total("1d12+1", random.Random(0))
        self.assertIn("1d12+1", dice5e._COMPILED)

    def test_crit_expr_doubles_dice_keeps_modifier(self):
        self.assertEqual(dice5e.crit_expr("1d10+3"), "2d10+3")
        self.assertEqual(dice5e.crit_expr("2d6"), "4d6")
        self.assertEqual(dice5e.crit_expr("1d8-1"), "2d8-1")


class TestDice(unittest.TestCase):
    def test_flat_and_dice(self):
        rng = random.Random(0)
        self.assertEqual(combat.roll("7", rng), 7)
        for _ in range(200):
            v = combat.roll("2d6+3", random.Random(_))
            self.assertTrue(5 <= v <= 15)

    def test_double_dice_keeps_modifier(self):
        self.assertEqual(combat._double_dice("1d10+3"), "2d10+3")
        self.assertEqual(combat._double_dice("2d6"), "4d6")
        self.assertEqual(combat._double_dice("1d8-1"), "2d8-1")


class TestStatblockFreshness(unittest.TestCase):
    def test_factories_return_independent_objects(self):
        a = statblocks.mind_forge_warden()
        b = statblocks.mind_forge_warden()
        a["hp"] = 0
        self.assertEqual(b["hp"], 75, "two builds must not share state")

    def test_build_encounter_tags_and_names(self):
        cs = statblocks.build_encounter("enforcers")
        sides = {c["side"] for c in cs}
        self.assertEqual(sides, {"party", "foe"})
        foe_names = [c["name"] for c in cs if c["side"] == "foe"]
        # duplicated foes get #1/#2 suffixes
        self.assertIn("Concord Enforcer #1", foe_names)
        self.assertIn("Concord Enforcer #2", foe_names)


class TestResistance(unittest.TestCase):
    def _engine(self):
        return combat.Combat([], random.Random(0))

    def test_typed_resistance_halves(self):
        eng = self._engine()
        bruiser = statblocks.engine_blooded_bruiser()
        dmg, resisted = eng._resisted(bruiser, 10, "force", magical=True)
        self.assertEqual((dmg, resisted), (5, True))

    def test_nonmagical_bps_halved_but_magical_full(self):
        eng = self._engine()
        warden = statblocks.mind_forge_warden()
        self.assertEqual(eng._resisted(warden, 8, "piercing", magical=False), (4, True))
        self.assertEqual(eng._resisted(warden, 8, "force", magical=True), (8, False))

    def test_unresisted_full(self):
        eng = self._engine()
        scout = statblocks.tide_scout_pc()
        self.assertEqual(eng._resisted(scout, 9, "slashing", magical=False), (9, False))


class TestTurnMechanics(unittest.TestCase):
    def test_dead_combatant_does_not_act(self):
        atk = statblocks.warforged_pc(); atk["side"] = "party"; atk["hp"] = 0
        foe = statblocks.aether_construct(); foe["side"] = "foe"
        eng = combat.Combat([atk, foe], random.Random(1))
        eng.take_turn(atk)
        self.assertEqual(foe["hp"], foe["max_hp"], "a downed creature must not attack")

    def test_stunned_creature_loses_its_turn(self):
        atk = statblocks.aether_construct(); atk["side"] = "foe"; atk["skip_turns"] = 1
        foe = statblocks.warforged_pc(); foe["side"] = "party"
        eng = combat.Combat([atk, foe], random.Random(1))
        eng.take_turn(atk)
        self.assertEqual(foe["hp"], foe["max_hp"], "a stunned creature deals no damage")
        self.assertEqual(atk["skip_turns"], 0, "the skipped turn is consumed")

    def test_zero_hp_removes_from_living(self):
        a = statblocks.sena_koll(); a["side"] = "party"
        b = statblocks.aether_construct(); b["side"] = "foe"; b["hp"] = 0
        eng = combat.Combat([a, b], random.Random(0))
        self.assertEqual([c["name"] for c in eng.living("foe")], [])
        self.assertEqual(len(eng.living("party")), 1)


class TestFightDeterminismAndResolution(unittest.TestCase):
    def test_same_seed_same_fight(self):
        for enc in statblocks.ENCOUNTERS:
            with self.subTest(encounter=enc):
                r1 = combat.Combat(statblocks.build_encounter(enc), random.Random(9)).run()
                r2 = combat.Combat(statblocks.build_encounter(enc), random.Random(9)).run()
                self.assertEqual(r1, r2)

    def test_every_encounter_resolves(self):
        for enc in statblocks.ENCOUNTERS:
            with self.subTest(encounter=enc):
                res = combat.Combat(statblocks.build_encounter(enc), random.Random(4)).run()
                self.assertIn(res["outcome"], ("party", "foe", "stalemate"))
                self.assertGreaterEqual(res["rounds"], 1)

    def test_simulate_counts_sum_to_runs(self):
        s = combat.simulate("raiders", 40)
        self.assertEqual(sum(s["wins"].values()), 40)
        self.assertTrue(0 <= s["tpk"] <= 40)


class TestLedgerIntegration(unittest.TestCase):
    def test_logged_fight_verifies_and_tamper_refuses(self):
        box = tempfile.mkdtemp(prefix="aetheris-combat-test-")
        try:
            sink = LedgerSink(box)
            sink.open_session("combat-test", {"encounter": "warden"})
            cs = statblocks.build_encounter("warden")
            res = combat.Combat(cs, random.Random(3), sink=sink).run()
            sink.close_session(res)
            self.assertTrue(sink.verify(), sink._last_verify_output)
            sink.close()

            # forbidden act: rewrite a logged row -> the chain must refuse.
            con = sqlite3.connect(os.path.join(box, "campaign.db"))
            # SELECT the id, then UPDATE by id: `UPDATE ... LIMIT` needs SQLite built
            # with SQLITE_ENABLE_UPDATE_DELETE_LIMIT, which stock CPython often lacks.
            rid = con.execute("SELECT id FROM ledger WHERE kind='turn' "
                              "ORDER BY id DESC LIMIT 1").fetchone()[0]
            con.execute("UPDATE ledger SET note = note || ' (edited)' WHERE id=?", (rid,))
            con.commit(); con.close()
            verify_py = combat.AGM_VERIFY
            r = subprocess.run([sys.executable, verify_py,
                                os.path.join(box, "campaign.db"), "--canon"],
                               capture_output=True, text=True)
            self.assertNotEqual(r.returncode, 0, "a tampered combat log must NOT verify")
            self.assertIn("does not match", (r.stdout + r.stderr))
        finally:
            shutil.rmtree(box, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
