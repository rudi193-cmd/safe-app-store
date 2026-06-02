"""Unit tests for TUI route helpers."""

from __future__ import annotations

import unittest

import tui_routes
from tui_routes import RouteFrame, breadcrumb_text, footer_hints


class TuiRoutesTests(unittest.TestCase):
    def test_breadcrumb_single_home(self) -> None:
        stack = [RouteFrame("home", label="Today")]
        self.assertEqual(breadcrumb_text(stack), "Today")

    def test_breadcrumb_drill_down(self) -> None:
        stack = [
            RouteFrame("home", label="Today"),
            RouteFrame("matters", label="Matters"),
            RouteFrame("matter_items", params={"matter": "coparent"}, label="Coparent"),
        ]
        self.assertEqual(breadcrumb_text(stack), "Today › Matters › Coparent")

    def test_footer_hints_home_includes_toggle(self) -> None:
        hints = footer_hints("home", show_resolved=False)
        self.assertIn("m matters", hints)
        self.assertIn("t toggle resolved", hints)
        self.assertIn("hiding resolved", hints)

    def test_footer_hints_drafts_open(self) -> None:
        hints = footer_hints("drafts", show_resolved=False)
        self.assertIn("o open draft", hints)

    def test_footer_hints_fact_review_includes_ai_inspect(self) -> None:
        hints = footer_hints("fact_review", show_resolved=False)
        self.assertIn("f AI inspect", hints)
        self.assertIn("Shift+f re-inspect", hints)

    def test_matter_nav_entries(self) -> None:
        keys = {m[0] for m in tui_routes.MATTER_NAV}
        self.assertIn("coparent", keys)
        self.assertIn("cross_case", keys)


if __name__ == "__main__":
    unittest.main()
