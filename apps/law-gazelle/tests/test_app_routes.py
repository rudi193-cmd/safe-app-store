"""Textual pilot tests for Law Gazelle drill-down navigation."""

from __future__ import annotations

import unittest
from unittest import mock

try:
    from app import LawGazelleApp
    from tui_routes import breadcrumb_text

    HAS_TEXTUAL = LawGazelleApp is not None
except ImportError:
    HAS_TEXTUAL = False


@unittest.skipUnless(HAS_TEXTUAL, "textual not installed")
class AppRoutePilotTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._sync_patch = mock.patch(
            "app._sync_and_report",
            return_value={
                "dest": "/tmp/cases",
                "copied": [],
                "missing": [],
                "optional_missing": [],
                "artifacts": [],
            },
        )
        self._today_patch = mock.patch(
            "app.workflow.today_cards",
            return_value=[
                {
                    "card_id": "coparent:atom:ATM-001",
                    "matter": "Coparent",
                    "status_label": "Due Soon",
                    "recommended_action_label": "Draft schedule response",
                    "why": "Schedule item",
                    "title": "Test atom",
                    "source_db": "workflow",
                    "item_type": "action_card",
                    "item_id": "coparent:atom:ATM-001",
                    "source_item": {
                        "case": "coparent",
                        "source_db": "coparent",
                        "kind": "atom",
                        "item_type": "atom",
                        "item_id": "ATM-001",
                        "atom_id": "ATM-001",
                        "domain": "schedule",
                    },
                }
            ],
        )
        self._milestone_patch = mock.patch("app.milestone_banner", return_value="")
        self._urgent_patch = mock.patch("app.urgent_queue", return_value=[])
        self._sync_patch.start()
        self._today_patch.start()
        self._urgent_patch.start()
        self._milestone_patch.start()

    async def asyncTearDown(self) -> None:
        self._milestone_patch.stop()
        self._urgent_patch.stop()
        self._today_patch.stop()
        self._sync_patch.stop()

    async def test_starts_on_today_home(self) -> None:
        app = LawGazelleApp()
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            self.assertIn("Today", breadcrumb_text(app._route_stack))
            self.assertEqual(app._current_route, "home")

    async def test_enter_opens_action_deck(self) -> None:
        app = LawGazelleApp()
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            self.assertEqual(app._current_route, "action_deck")
            self.assertIsNotNone(app._active_card)

    async def test_m_opens_matters(self) -> None:
        app = LawGazelleApp()
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            await pilot.press("m")
            await pilot.pause()
            self.assertEqual(app._current_route, "matters")
            self.assertIn("Matters", breadcrumb_text(app._route_stack))

    async def test_escape_returns_from_matters(self) -> None:
        app = LawGazelleApp()
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            await pilot.press("m")
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            self.assertEqual(app._current_route, "home")

    async def test_d_opens_drafts(self) -> None:
        app = LawGazelleApp()
        with mock.patch("app.document_store.list_drafts", return_value=[]):
            async with app.run_test(size=(100, 30)) as pilot:
                await pilot.pause()
                await pilot.press("d")
                await pilot.pause()
                self.assertEqual(app._current_route, "drafts")

    async def test_a_opens_activity_with_commit_rows(self) -> None:
        """Commit events have null source_db/item_type/item_id — keys must stay unique."""
        duplicate_ts = "2099-06-02T06:27:35Z"
        events = [
            {
                "event_type": "commit",
                "summary": "Session commit: First commit (2 files)",
                "source_db": None,
                "item_type": None,
                "item_id": None,
                "created_at": duplicate_ts,
            },
            {
                "event_type": "commit",
                "summary": "Session commit: Atoms updated (2 files)",
                "source_db": None,
                "item_type": None,
                "item_id": None,
                "created_at": duplicate_ts,
            },
        ]
        app = LawGazelleApp()
        with mock.patch("app.gazelle_state.list_activity", return_value=events):
            async with app.run_test(size=(100, 30)) as pilot:
                await pilot.pause()
                await pilot.press("a")
                await pilot.pause()
                self.assertEqual(app._current_route, "activity")
                keys = list(app._item_by_key.keys())
                self.assertEqual(len(keys), len(set(keys)))


if __name__ == "__main__":
    unittest.main()
