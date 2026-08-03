"""Tests for the deadlock, and for the tests.

The load-bearing one is ``test_the_gate_can_fail``. Everything else here checks
that the building is unsolvable; that test checks that "unsolvable" is a
measurement rather than a mood, by installing the single office that would break
the deadlock and confirming the verdict flips.
"""
from __future__ import annotations

import random
import unittest

from bureau import graph as G
from bureau import verify
from bureau.napkin import NO_NAPKIN, Goo, Napkin
from bureau.play import NAPKIN_BLANK, NAPKIN_WORD, Session


class TestTheBuilding(unittest.TestCase):
    def test_building_deadlocks(self):
        proof = verify.prove()
        self.assertTrue(proof.deadlocked, proof.explain())
        self.assertNotIn(G.GOAL, proof.obtainable)

    def test_the_missing_documents_are_the_ones_we_think(self):
        """Three prerequisites have no issuer anywhere in the building."""
        proof = verify.prove()
        self.assertEqual(proof.unissuable, frozenset({"attestation_presence", "note_judged", "filing_resolved"}))

    def test_the_gate_can_fail(self):
        """Break it deliberately; confirm the verdict flips.

        Issue all three never-issued documents and the building opens. If this
        does not flip, "unreachable" was never a measurement.
        """
        mutated = verify.with_mutant_issuers(
            "attestation_presence", "note_judged", "filing_resolved"
        )
        proof = verify.prove(offices=mutated)
        self.assertFalse(proof.deadlocked, proof.explain())
        self.assertIn(G.GOAL, proof.obtainable)

    def test_one_mutation_is_not_enough(self):
        """Three documents are missing; fixing one must not open the building."""
        mutated = verify.with_mutant_issuer("attestation_presence")
        self.assertTrue(verify.prove(offices=mutated).deadlocked)

    def test_mutating_an_irrelevant_document_does_not_flip_it(self):
        mutated = verify.with_mutant_issuer("ticket", office_id="another_queue")
        self.assertTrue(verify.prove(offices=mutated).deadlocked)

    def test_gerald_issues_nothing(self):
        self.assertIsNone(G.GERALD.issues)
        for doc in ("attestation_presence", "note_judged", "filing_resolved"):
            self.assertEqual(G.issuers_of(doc), [], doc)

    def test_every_office_states_a_rule(self):
        for office in G.OFFICES.values():
            with self.subTest(office=office.id):
                self.assertTrue(office.rule.strip(), "an office with no rule is a villain")


class TestFalseProgress(unittest.TestCase):
    """The design is the gap between what you can hold and what counts."""

    def test_the_building_looks_winnable(self):
        """Credulous search — matching on kind, the way a player reads a docket
        — reaches the goal. If it did not, there would be no false hope to feel."""
        proof = verify.prove()
        self.assertTrue(proof.looks_winnable, proof.explain())
        self.assertTrue(proof.deadlocked, "and yet")

    def test_every_false_summit_is_obtainable_and_useless(self):
        proof = verify.prove()
        self.assertEqual(
            proof.false_summits,
            frozenset({"attestation_room", "note_passing", "filing_slant"}),
        )
        for doc in proof.false_summits:
            with self.subTest(doc=doc):
                self.assertIn(doc, proof.obtainable, "must be gettable to disappoint")
                self.assertNotIn(doc, proof.unissuable)

    def test_each_false_summit_shares_a_kind_with_something_missing(self):
        """That shared kind is the whole trick: the docket shows kind, the desk
        checks the fine print."""
        proof = verify.prove()
        missing_kinds = {G.DOCS[d].kind for d in proof.unissuable}
        for doc in proof.false_summits:
            with self.subTest(doc=doc):
                self.assertIn(G.DOCS[doc].kind, missing_kinds)


class TestNoStrategyWins(unittest.TestCase):
    def test_random_play_never_obtains_the_goal_documents(self):
        """10k random walks through the building. None of them get anywhere."""
        rng = random.Random(1989)
        ids = list(G.OFFICES)
        for trial in range(10_000):
            s = Session(seed=trial)
            for _ in range(12):
                s.visit(rng.choice(ids))
            with self.subTest(trial=trial):
                self.assertNotIn(G.GOAL, s.held)


class TestTheNapkin(unittest.TestCase):
    def test_blank_is_not_absence(self):
        """A blank napkin is a recorded value. No napkin is a missing row."""
        self.assertIsNot(Napkin.BLANK, NO_NAPKIN)
        self.assertIsNotNone(Napkin.BLANK)
        self.assertIsNone(NO_NAPKIN)
        self.assertNotEqual(Napkin.BLANK.value, NO_NAPKIN)

    def test_blank_and_absent_resolve_differently(self):
        """The distinction is mechanical, not decorative."""
        blank = Session(seed=0)
        blank.held.add(NAPKIN_BLANK)
        self.assertIn("VOIDED", blank.hand("records")[0])
        self.assertEqual(blank.resolution, "voided")

        absent = Session(seed=0)
        self.assertIsNone(absent.resolution)
        absent.hand("records")
        self.assertIsNone(absent.resolution, "no napkin must not resolve anything")

    def test_surprise_gates_the_goo(self):
        """Nothing declares itself while the narrator can still be surprised."""
        goo = Goo(seed=3)
        self.assertFalse(goo.visible)
        for _ in range(500):
            self.assertIs(goo.tick(), NO_NAPKIN)
        while goo.spend_surprise():
            pass
        self.assertTrue(goo.visible)

    def test_the_threshold_is_not_immediate(self):
        goo = Goo(seed=7)
        while goo.spend_surprise():
            pass
        self.assertIs(goo.tick(), NO_NAPKIN, "it should never land on the first dwell")

    def test_grape_resets_the_wait(self):
        seen_grape = False
        for seed in range(200):
            goo = Goo(seed=seed)
            while goo.spend_surprise():
                pass
            for _ in range(60):
                if goo.tick() is Napkin.GRAPE:
                    seen_grape = True
                    self.assertEqual(goo.dwell, 0, "a grape restarts the wait")
                    break
            if seen_grape:
                break
        self.assertTrue(seen_grape, "grape face is unreachable — check the weights")


class TestPersistenceWins(unittest.TestCase):
    def test_showing_up_always_resolves(self):
        """The building is unsolvable; the game is not unwinnable.

        A player with no strategy beyond returning resolves every seed. If this
        regresses, the deadlock proof above is still true and the artifact is
        merely cruel.
        """
        for seed in range(120):
            s = Session(seed=seed)
            for _ in range(400):
                if NAPKIN_WORD in s.held:
                    s.hand("hanz")
                elif NAPKIN_BLANK in s.held:
                    s.hand("records")
                if s.resolution:
                    break
                s.visit("gerald")
            with self.subTest(seed=seed):
                self.assertIn(s.resolution, ("enrolled", "voided"))

    def test_both_endings_are_reachable(self):
        endings = set()
        for seed in range(120):
            s = Session(seed=seed)
            for _ in range(400):
                if NAPKIN_WORD in s.held:
                    s.hand("hanz")
                elif NAPKIN_BLANK in s.held:
                    s.hand("records")
                if s.resolution:
                    endings.add(s.resolution)
                    break
                s.visit("gerald")
        self.assertEqual(endings, {"enrolled", "voided"})


if __name__ == "__main__":
    unittest.main()
