"""Grading must reward real answers, not substring accidents."""

from __future__ import annotations

import unittest

from civics.scoring import answer_matches


class ScoringTests(unittest.TestCase):
    def test_current_party_accepts_republican_rejects_democrat(self):
        accepted = [
            "Republican",
            "Republican Party",
            "the Republican Party",
            "GOP",
        ]
        self.assertTrue(answer_matches("Republican", accepted))
        self.assertTrue(answer_matches("GOP", accepted))
        self.assertFalse(answer_matches("Democratic", accepted))
        self.assertFalse(answer_matches("Democrat", accepted))

    def test_two_party_question_needs_both(self):
        accepted = [
            "Democratic and Republican",
            "Democratic Party and Republican Party",
            "Republican and Democratic",
        ]
        self.assertTrue(answer_matches("Democratic and Republican", accepted))
        self.assertFalse(answer_matches("Republican", accepted))
        self.assertFalse(answer_matches("republic", accepted))

    def test_no_prefix_or_half_token_shortcuts(self):
        self.assertFalse(answer_matches("civil rights", ["civil rights movement"]))
        self.assertFalse(answer_matches("free", ["freedom of speech"]))

    def test_name_spelling_slack(self):
        self.assertTrue(answer_matches("washingtin", ["George Washington"]))
        self.assertTrue(answer_matches("Trump", ["Donald Trump"]))

    def test_numbers_strict(self):
        self.assertFalse(answer_matches("16", ["6"]))
        self.assertTrue(answer_matches("twenty seven", ["27"]))


if __name__ == "__main__":
    unittest.main()
