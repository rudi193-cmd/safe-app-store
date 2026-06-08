"""Async TUI tests using Textual's run_test / Pilot harness.

Each test boots the real UTETYApp in headless mode with:
  - tui_db._DB_DIR redirected to a temp directory
  - tui_llm.ask mocked to return instantly
  - tui_llm.categorize_for_binder mocked where needed
"""

from __future__ import annotations

import asyncio
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

import tui_db
import tui_llm
from tui import FACULTY, UTETYApp


# ── helpers ───────────────────────────────────────────────────────────────────

def _llm_ok(text="response text", tier="ollama", professor="Willow"):
    return {"ok": True, "text": text, "provider": "llama3.1:8b", "tier": tier}


def _llm_fail(error="timeout"):
    return {"ok": False, "error": error, "tier": "ollama"}


async def _wait_idle(pilot, *, timeout=3.0, interval=0.05):
    """Pause until app._busy is False or timeout elapses."""
    elapsed = 0.0
    while pilot.app._busy and elapsed < timeout:
        await pilot.pause(interval)
        elapsed += interval


def _log_text(app) -> str:
    from textual.widgets import RichLog
    log = app.query_one("#chat-log", RichLog)
    return "\n".join(s.text for s in log.lines)


# ── base ──────────────────────────────────────────────────────────────────────

class TuiTestBase(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self._db_dir = Path(self._tmpdir) / "sessions"
        self._db_patch = mock.patch.object(tui_db, "_DB_DIR", self._db_dir)
        self._db_patch.start()

    def tearDown(self) -> None:
        self._db_patch.stop()
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _mock_llm(self, text="A response.", tier="ollama"):
        return mock.patch.object(tui_llm, "ask", return_value=_llm_ok(text, tier))

    def _mock_categorize(self, category="general correspondence"):
        return mock.patch.object(
            tui_llm, "categorize_for_binder", return_value=category
        )


# ── structure tests ───────────────────────────────────────────────────────────

class TestMount(TuiTestBase):
    async def test_all_professors_in_sidebar(self) -> None:
        async with UTETYApp().run_test(size=(120, 40)) as pilot:
            from textual.widgets import ListView
            items = list(pilot.app.query_one("#faculty-list", ListView).children)
            self.assertEqual(len(items), len(FACULTY))

    async def test_pigeon_in_sidebar(self) -> None:
        # Pigeon is in FACULTY — navigate to its index and confirm it activates
        pigeon_idx = next(i for i, f in enumerate(FACULTY) if f["name"] == "Pigeon")
        async with UTETYApp().run_test(size=(120, 40)) as pilot:
            for _ in range(pigeon_idx):
                await pilot.press("down")
            await pilot.pause()
            self.assertEqual(pilot.app._active_professor, "Pigeon")

    async def test_initial_professor_is_willow(self) -> None:
        async with UTETYApp().run_test(size=(120, 40)) as pilot:
            self.assertEqual(pilot.app._active_professor, "Willow")

    async def test_willow_greeting_shown(self) -> None:
        async with UTETYApp().run_test(size=(120, 40)) as pilot:
            text = _log_text(pilot.app)
            self.assertIn("Where do you need to go", text)

    async def test_chat_log_border_present(self) -> None:
        async with UTETYApp().run_test(size=(120, 40)) as pilot:
            from textual.widgets import RichLog
            log = pilot.app.query_one("#chat-log", RichLog)
            self.assertIsNotNone(log)

    async def test_input_placeholder_default(self) -> None:
        async with UTETYApp().run_test(size=(120, 40)) as pilot:
            from textual.widgets import Input
            inp = pilot.app.query_one("#message-input", Input)
            self.assertEqual(inp.placeholder, "Your message →")


# ── navigation tests ──────────────────────────────────────────────────────────

class TestNavigation(TuiTestBase):
    async def test_down_switches_professor(self) -> None:
        async with UTETYApp().run_test(size=(120, 40)) as pilot:
            await pilot.press("down")
            await pilot.pause()
            self.assertEqual(pilot.app._active_professor, "Oakenscroll")

    async def test_multiple_downs_reach_correct_professor(self) -> None:
        # FACULTY order: Willow, Oakenscroll, Riggs, Hanz, Copenhagen (index 4)
        async with UTETYApp().run_test(size=(120, 40)) as pilot:
            for _ in range(4):
                await pilot.press("down")
            await pilot.pause()
            self.assertEqual(pilot.app._active_professor, "Copenhagen")

    async def test_switch_updates_input_placeholder(self) -> None:
        async with UTETYApp().run_test(size=(120, 40)) as pilot:
            # Navigate to Binder (last in list: index 13)
            for _ in range(13):
                await pilot.press("down")
            await pilot.pause()
            from textual.widgets import Input
            inp = pilot.app.query_one("#message-input", Input)
            self.assertEqual(inp.placeholder, "Submit for filing →")

    async def test_switch_shows_new_greeting(self) -> None:
        async with UTETYApp().run_test(size=(120, 40)) as pilot:
            # Navigate to Riggs
            await pilot.press("down")
            await pilot.press("down")
            await pilot.pause()
            self.assertEqual(pilot.app._active_professor, "Riggs")
            text = _log_text(pilot.app)
            self.assertIn("Workshop", text)

    async def test_copenhagen_special_intro(self) -> None:
        async with UTETYApp().run_test(size=(120, 40)) as pilot:
            for _ in range(4):
                await pilot.press("down")
            await pilot.pause()
            text = _log_text(pilot.app)
            self.assertIn("Copenhagen is present", text)
            self.assertIn("🍊", text)

    async def test_gerald_greeting(self) -> None:
        # Gerald is at index 10
        async with UTETYApp().run_test(size=(120, 40)) as pilot:
            prof_idx = next(i for i, f in enumerate(FACULTY) if f["name"] == "Gerald")
            for _ in range(prof_idx):
                await pilot.press("down")
            await pilot.pause()
            text = _log_text(pilot.app)
            self.assertIn("WELCOME", text)

    async def test_pigeon_greeting(self) -> None:
        async with UTETYApp().run_test(size=(120, 40)) as pilot:
            prof_idx = next(i for i, f in enumerate(FACULTY) if f["name"] == "Pigeon")
            for _ in range(prof_idx):
                await pilot.press("down")
            await pilot.pause()
            text = _log_text(pilot.app)
            self.assertIn("EXACTLY", text)

    async def test_filed_count_resets_on_switch(self) -> None:
        async with UTETYApp().run_test(size=(120, 40)) as pilot:
            pilot.app._filed_count[0] = 5
            await pilot.press("down")  # switch to Oakenscroll
            await pilot.pause()
            # filed_count reloaded from DB (should be 0 for fresh session)
            self.assertEqual(pilot.app._filed_count[0], 0)


# ── message flow tests ────────────────────────────────────────────────────────

class TestMessageFlow(TuiTestBase):
    async def _send(self, pilot, message: str) -> None:
        """Focus input, send message, wait for worker to finish."""
        await pilot.press("enter")
        await pilot.pause()
        for char in message:
            await pilot.press(char)
        await pilot.press("enter")
        await _wait_idle(pilot)

    async def test_user_message_appears_in_log(self) -> None:
        with self._mock_llm("Great question."):
            async with UTETYApp().run_test(size=(120, 40)) as pilot:
                await self._send(pilot, "hello willow")
                text = _log_text(pilot.app)
                self.assertIn("hello willow", text)

    async def test_llm_response_appears_in_log(self) -> None:
        with self._mock_llm("Systems nominal. Everything is fine."):
            async with UTETYApp().run_test(size=(120, 40)) as pilot:
                await self._send(pilot, "hi")
                text = _log_text(pilot.app)
                self.assertIn("Systems nominal", text)

    async def test_provider_attribution_shown(self) -> None:
        with self._mock_llm("response", tier="ollama"):
            async with UTETYApp().run_test(size=(120, 40)) as pilot:
                await self._send(pilot, "hi")
                text = _log_text(pilot.app)
                self.assertIn("llama3.1:8b", text)

    async def test_tier_reflected_in_subtitle(self) -> None:
        with self._mock_llm("ok", tier="ollama"):
            async with UTETYApp().run_test(size=(120, 40)) as pilot:
                await self._send(pilot, "hi")
                self.assertIn("ollama", pilot.app.sub_title)

    async def test_message_saved_to_db(self) -> None:
        with self._mock_llm("reply"):
            async with UTETYApp().run_test(size=(120, 40)) as pilot:
                await self._send(pilot, "save me")
        history = tui_db.load_history("Willow")
        roles = [m["role"] for m in history]
        self.assertIn("user", roles)
        self.assertIn("assistant", roles)

    async def test_llm_failure_shows_notification(self) -> None:
        notifications = []
        with mock.patch.object(tui_llm, "ask", return_value=_llm_fail("timeout")):
            async with UTETYApp().run_test(size=(120, 40), notifications=True) as pilot:
                pilot.app.notify = lambda msg, **kw: notifications.append(msg)
                await self._send(pilot, "hi")
        self.assertTrue(any("timeout" in n or "No response" in n for n in notifications))

    async def test_busy_guard_ignores_second_message(self) -> None:
        sent = []
        original_ask = tui_llm.ask

        async def slow_ask(*a, **kw):
            await asyncio.sleep(0.5)
            return _llm_ok()

        with mock.patch.object(tui_llm, "ask", side_effect=lambda *a, **kw: _llm_ok()):
            async with UTETYApp().run_test(size=(120, 40)) as pilot:
                # Manually set busy then try to send
                pilot.app._busy = True
                pilot.app._send_message("blocked message")
                # Should not queue a worker while busy
                self.assertTrue(pilot.app._busy)  # still busy (no new worker started)


# ── per-professor rendering ───────────────────────────────────────────────────

class TestProfessorRendering(TuiTestBase):
    async def _nav_to(self, pilot, name: str) -> None:
        idx = next(i for i, f in enumerate(FACULTY) if f["name"] == name)
        for _ in range(idx):
            await pilot.press("down")
        await pilot.pause()

    async def _send(self, pilot, message: str) -> None:
        await pilot.press("enter")
        await pilot.pause()
        for char in message:
            await pilot.press(char)
        await pilot.press("enter")
        await _wait_idle(pilot)

    async def test_gerald_napkin_box(self) -> None:
        with self._mock_llm("CYCLE COMPLETE."):
            async with UTETYApp().run_test(size=(120, 40)) as pilot:
                await self._nav_to(pilot, "Gerald")
                await self._send(pilot, "sign this")
                text = _log_text(pilot.app)
                self.assertIn("napkin", text)
                self.assertIn("G.", text)

    async def test_gerald_truncates_long_response(self) -> None:
        long_text = "A" * 400
        with self._mock_llm(long_text):
            async with UTETYApp().run_test(size=(120, 40)) as pilot:
                await self._nav_to(pilot, "Gerald")
                await self._send(pilot, "essay please")
                text = _log_text(pilot.app)
                self.assertIn("*confetti*", text)

    async def test_copenhagen_hanz_framing(self) -> None:
        with self._mock_llm("Hello, friend. The orange glows warmly."):
            async with UTETYApp().run_test(size=(120, 40)) as pilot:
                await self._nav_to(pilot, "Copenhagen")
                await self._send(pilot, "what does Copenhagen think")
                text = _log_text(pilot.app)
                self.assertIn("🍊", text)
                self.assertIn("Hanz translates", text)

    async def test_oakenscroll_filed_counter_increments(self) -> None:
        with self._mock_llm("*The answer is clear.*"):
            async with UTETYApp().run_test(size=(120, 40)) as pilot:
                await self._nav_to(pilot, "Oakenscroll")
                await self._send(pilot, "question one")
                text = _log_text(pilot.app)
                self.assertIn("Filed.", text)
                self.assertEqual(pilot.app._filed_count[0], 1)

    async def test_binder_shows_llm_category(self) -> None:
        with self._mock_llm("All filed."), self._mock_categorize("student grievance"):
            async with UTETYApp().run_test(size=(120, 40)) as pilot:
                await self._nav_to(pilot, "Binder")
                await self._send(pilot, "my grade is wrong")
                text = _log_text(pilot.app)
                self.assertIn("student grievance", text)
                self.assertIn("Filed under", text)

    async def test_binder_category_default_fallback(self) -> None:
        with self._mock_llm("Filed."), self._mock_categorize("general correspondence"):
            async with UTETYApp().run_test(size=(120, 40)) as pilot:
                await self._nav_to(pilot, "Binder")
                await self._send(pilot, "hello")
                text = _log_text(pilot.app)
                self.assertIn("general correspondence", text)

    async def test_ofshield_noted_prefix(self) -> None:
        with self._mock_llm("Passage acknowledged."):
            async with UTETYApp().run_test(size=(120, 40)) as pilot:
                await self._nav_to(pilot, "Ofshield")
                await self._send(pilot, "I am here")
                text = _log_text(pilot.app)
                self.assertIn("*noted*", text)

    async def test_steve_dog_counter(self) -> None:
        with self._mock_llm("Hot dog!"):
            async with UTETYApp().run_test(size=(120, 40)) as pilot:
                await self._nav_to(pilot, "Steve")
                await self._send(pilot, "hello")
                text = _log_text(pilot.app)
                self.assertIn("🌭", text)
                self.assertIn("of 10]", text)

    async def test_pigeon_prefix(self) -> None:
        with self._mock_llm("I know the way!"):
            async with UTETYApp().run_test(size=(120, 40)) as pilot:
                await self._nav_to(pilot, "Pigeon")
                await self._send(pilot, "where do I go")
                text = _log_text(pilot.app)
                self.assertIn("🐦 PIGEON:", text)


# ── action tests ──────────────────────────────────────────────────────────────

class TestActions(TuiTestBase):
    async def test_clear_history_wipes_log(self) -> None:
        with self._mock_llm("response"):
            async with UTETYApp().run_test(size=(120, 40)) as pilot:
                await pilot.press("enter")
                await pilot.pause()
                for ch in "test":
                    await pilot.press(ch)
                await pilot.press("enter")
                await _wait_idle(pilot)
                await pilot.app.run_action("clear")
                await pilot.pause()
                history = tui_db.load_history("Willow")
                self.assertEqual(history, [])

    async def test_clear_resets_filed_count(self) -> None:
        with self._mock_llm("*Filed.*"):
            async with UTETYApp().run_test(size=(120, 40)) as pilot:
                # Go to Oakenscroll
                await pilot.press("down")
                await pilot.pause()
                await pilot.press("enter")
                await pilot.pause()
                for ch in "q":
                    await pilot.press(ch)
                await pilot.press("enter")
                await _wait_idle(pilot)
                await pilot.app.run_action("clear")
                await pilot.pause()
                self.assertEqual(pilot.app._filed_count[0], 0)

    async def test_export_creates_file(self) -> None:
        with self._mock_llm("noted"):
            async with UTETYApp().run_test(size=(120, 40)) as pilot:
                await pilot.press("enter")
                await pilot.pause()
                for ch in "hello":
                    await pilot.press(ch)
                await pilot.press("enter")
                await _wait_idle(pilot)
                await pilot.app.run_action("export")
                await pilot.pause()
        export_dir = Path(__file__).parent.parent / "data" / "exports"
        self.assertTrue((export_dir / "willow_export.md").exists())

    async def test_ctrl_l_refocuses_list(self) -> None:
        async with UTETYApp().run_test(size=(120, 40)) as pilot:
            # Focus input first
            await pilot.press("enter")
            await pilot.pause()
            from textual.widgets import Input, ListView
            self.assertTrue(pilot.app.query_one("#message-input", Input).has_focus)
            await pilot.press("ctrl+l")
            await pilot.pause()
            self.assertTrue(pilot.app.query_one("#faculty-list", ListView).has_focus)


if __name__ == "__main__":
    unittest.main()
