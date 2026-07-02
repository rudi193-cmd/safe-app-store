"""Hero band rendering and context helpers."""

from __future__ import annotations

import unittest

import tui_art


class HeroArtTests(unittest.TestCase):
    def test_hero_field_default_height(self):
        field = tui_art.hero_field(90)
        self.assertEqual(len(field.plain.splitlines()), tui_art.HERO_ROWS)

    def test_fair_context_caption(self):
        ctx = tui_art.HeroContext(
            caption="⌂ Schoolhouse · Symbol Safari",
            fair_day="Citizenship Court · Naturalization",
            number_line="100 · civics questions on the test",
            canton="13",
            motto="E PLURIBUS UNUM",
        )
        text = tui_art.hero_field(100, ctx=ctx).plain
        self.assertIn("Schoolhouse", text)
        self.assertIn("Naturalization", text)
        self.assertIn("100", text)

    def test_solemn_card_detection(self):
        card = {"body": "It remains the deadliest war in American history"}
        self.assertTrue(tui_art.card_is_solemn(card))

    def test_party_official_line(self):
        card = {"legacy_id": 46, "prompt": "What is the political party of the President now?"}
        self.assertIn("Republican", tui_art.official_line_for_card(card))

    def test_landmark_accent_rights(self):
        card = {"pavilion": "rights_bingo", "tags": ["bill_of_rights"]}
        self.assertEqual(tui_art.card_landmark_accent(card), "liberty")


if __name__ == "__main__":
    unittest.main()
