"""Tests for the ledger bridge — mostly tests that it refuses to do things.

The bridge's whole value is a negative: it must not launder proofs into a
calibration ledger. Most of what follows checks that it declines.
"""
from __future__ import annotations

import unittest
from pathlib import Path

from bureau import ledger, verify

NOW = 1_780_000_000  # fixed; the module never reads a clock

# Set by hand for the tests, the way a person would. Deliberately not uniform —
# a caller who genuinely believes all six equally has not thought about them.
CONFS = {
    "no_issuer:attestation_presence": 0.9,
    "no_issuer:note_judged": 0.85,
    "no_issuer:filing_resolved": 0.8,
    "will_be_refused:attestation_room": 0.95,
    "will_be_refused:note_passing": 0.9,
    "will_be_refused:filing_slant": 0.9,
    "model_survives_remodelling": 0.65,
}


class TestItRefusesToLaunderProofs(unittest.TestCase):
    def test_no_claim_asserts_the_fixpoint(self):
        """The theorem must never appear as a prediction.

        If a claim ever says the search is correct, the ledger is being fed a
        certainty and its reliability diagram starts lying.
        """
        banned = ("fixpoint", "closure", "is unreachable", "the solver", "proved")
        for c in ledger.claims():
            for phrase in banned:
                with self.subTest(key=c.key, phrase=phrase):
                    self.assertNotIn(phrase, c.claim.lower())

    def test_every_claim_names_its_falsifier(self):
        for c in ledger.claims():
            with self.subTest(key=c.key):
                self.assertTrue(c.falsified_by.strip())
                self.assertNotEqual(c.falsified_by, c.claim)

    def test_confidence_is_never_invented(self):
        with self.assertRaises(ValueError) as e:
            ledger.emit({}, now=NOW)
        self.assertIn("not mine to guess", str(e.exception))

    def test_partial_confidences_are_refused(self):
        partial = dict(CONFS)
        partial.pop("model_survives_remodelling")
        with self.assertRaises(ValueError) as e:
            ledger.emit(partial, now=NOW)
        self.assertIn("model_survives_remodelling", str(e.exception))

    def test_out_of_range_confidence_is_refused(self):
        for bad in (0.0, 0.49, 1.0, 1.5):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    ledger.emit({**CONFS, "no_issuer:note_judged": bad}, now=NOW)


class TestTheRows(unittest.TestCase):
    def test_rows_match_state_claim_shape(self):
        rows = ledger.emit(CONFS, now=NOW)
        self.assertEqual(len(rows), len(CONFS))
        for r in rows:
            with self.subTest(claim=r["claim"][:40]):
                self.assertEqual(set(r), {"claim", "confidence", "due", "tags"})
                self.assertTrue(r["claim"].strip())
                self.assertGreater(r["due"], NOW)
                self.assertIn("bureau", r["tags"])

    def test_findings_are_covered_one_for_one(self):
        proof = verify.prove()
        keys = {c.key for c in ledger.claims()}
        for doc in proof.unissuable:
            self.assertIn(f"no_issuer:{doc}", keys)
        for doc in proof.false_summits:
            self.assertIn(f"will_be_refused:{doc}", keys)
        self.assertIn("model_survives_remodelling", keys)

    def test_the_fidelity_claim_is_always_present(self):
        """Even a graph with no findings still carries modelling risk."""
        empty = verify.prove(offices=verify.with_mutant_issuers(
            "attestation_presence", "note_judged", "filing_resolved"))
        self.assertFalse(empty.deadlocked)
        keys = {c.key for c in ledger.claims(proof=empty)}
        self.assertIn("model_survives_remodelling", keys)


class TestTheDuplicatedBounds(unittest.TestCase):
    """CONF_MIN/CONF_MAX are copied across a repo boundary and can drift."""

    SOURCE = Path("/workspace/safe-app-store/apps/oakenscrolls-office/office_db.py")

    def test_bounds_match_the_real_ledger(self):
        if not self.SOURCE.exists():
            self.skipTest(
                f"no oakenscrolls-office checkout at {self.SOURCE} — the bounds in "
                "bureau/ledger.py are UNVERIFIED in this environment"
            )
        line = next(
            ln for ln in self.SOURCE.read_text().splitlines()
            if ln.startswith("CONF_MIN, CONF_MAX")
        )
        self.assertIn(f"{ledger.CONF_MIN}, {ledger.CONF_MAX}", line)


if __name__ == "__main__":
    unittest.main()
