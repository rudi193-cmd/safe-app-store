"""Tests for prompt building and response formatting in consult_engine."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

import consult_engine


# Minimal catalog for tests that call faculty_context / course_context
_MINIMAL_CATALOG = {
    "meta": {"title": "UTETY", "mottos": ["Non Veritas Sed Vibrae", "Come again"]},
    "faculty": [
        {
            "name": "Riggs",
            "dept": "Applied Reality Engineering",
            "location": "The Workshop",
            "bio": "We do not guess. We measure.",
            "course": "MECH 101",
        },
        {
            "name": "Hanz",
            "dept": "Computational Kindness",
            "location": "The Candlelit Corner",
            "bio": "Parables and AI literacy.",
            "course": "CODE 101",
        },
    ],
    "courses": [
        {
            "code": "MECH 101",
            "title": "Measurement Fundamentals",
            "desc": "We measure things.",
            "instructor": "Riggs",
        }
    ],
}


class BuildPromptTests(unittest.TestCase):
    def setUp(self) -> None:
        # Patch PERSONAS and UTETY_CONTEXT so tests are hermetic
        # Use realistically-sized values so compact < full holds in size comparisons
        _long_persona = "You are Riggs. " + ("We measure. " * 60)
        _long_context = "UTETY is a strange university. " + ("Non Veritas Sed Vibrae. " * 80)
        self._patch_personas = mock.patch.object(
            consult_engine,
            "PERSONAS",
            {
                "Willow": "You are Willow. " + "W" * 200,
                "Riggs": _long_persona,
                "Hanz": "You are Hanz. " + "H" * 200,
                "Copenhagen": "You are Copenhagen. " + "C" * 200,
            },
        )
        self._patch_context = mock.patch.object(
            consult_engine, "UTETY_CONTEXT", _long_context
        )
        self._patch_personas.start()
        self._patch_context.start()

    def tearDown(self) -> None:
        self._patch_personas.stop()
        self._patch_context.stop()

    def _build(self, professor, history=None, **kwargs):
        return consult_engine.build_prompt(professor, history or [], **kwargs)

    # ── basic structure ───────────────────────────────────────────────────────

    def test_contains_persona_and_context(self) -> None:
        prompt = self._build("Willow")
        self.assertIn("You are Willow.", prompt)
        self.assertIn("UTETY is a strange university.", prompt)

    def test_history_included(self) -> None:
        history = [
            {"role": "user", "content": "what time is it"},
            {"role": "assistant", "content": "always"},
        ]
        prompt = self._build("Willow", history)
        self.assertIn("what time is it", prompt)
        self.assertIn("always", prompt)

    def test_ends_with_professor_label(self) -> None:
        prompt = self._build("Riggs")
        self.assertTrue(prompt.strip().endswith("Riggs:"))

    def test_history_limit_compact(self) -> None:
        history = [{"role": "user", "content": f"msg{i}"} for i in range(10)]
        prompt = self._build("Willow", history, compact=True)
        # compact limits to 4 recent messages — early messages should be absent
        self.assertNotIn("msg0", prompt)
        self.assertIn("msg9", prompt)

    def test_history_limit_full(self) -> None:
        history = [{"role": "user", "content": f"msg{i}"} for i in range(15)]
        prompt = self._build("Willow", history)
        self.assertNotIn("msg0", prompt)
        self.assertIn("msg14", prompt)

    # ── Copenhagen / Hanz framing ─────────────────────────────────────────────

    def test_copenhagen_uses_hanz_persona(self) -> None:
        prompt = self._build("Copenhagen")
        self.assertIn("You are Hanz", prompt)
        self.assertNotIn("You are Copenhagen (not used directly).", prompt)

    def test_copenhagen_prepends_translator_framing(self) -> None:
        prompt = self._build("Copenhagen")
        self.assertIn("Hanz translates", prompt)
        self.assertIn("Hello, friend.", prompt)

    def test_copenhagen_speaker_label_is_hanz(self) -> None:
        prompt = self._build("Copenhagen")
        self.assertTrue(prompt.strip().endswith("Hanz:"))
        self.assertNotIn("\nCopenhagen:", prompt)

    # ── compact mode ──────────────────────────────────────────────────────────

    def test_compact_uses_short_context(self) -> None:
        with mock.patch.object(consult_engine, "_load_catalog", return_value=_MINIMAL_CATALOG):
            prompt = self._build("Riggs", compact=True)
        self.assertIn("UTETY", prompt)
        self.assertNotIn("UTETY is a strange university.", prompt)  # full context not used

    def test_compact_much_shorter_than_full(self) -> None:
        with mock.patch.object(consult_engine, "_load_catalog", return_value=_MINIMAL_CATALOG):
            compact = self._build("Riggs", compact=True)
            full = self._build("Riggs", compact=False)
        self.assertLess(len(compact), len(full))

    # ── professor_memory and willow_context ───────────────────────────────────

    def test_professor_memory_injected(self) -> None:
        prompt = self._build("Riggs", professor_memory="Riggs once built a perpetual motion machine.")
        self.assertIn("Riggs's Memory:", prompt)
        self.assertIn("perpetual motion machine", prompt)

    def test_professor_memory_appears_before_history(self) -> None:
        history = [{"role": "user", "content": "test"}]
        prompt = self._build("Riggs", history, professor_memory="memory content")
        mem_pos = prompt.index("memory content")
        hist_pos = prompt.index("### Conversation History:")
        self.assertLess(mem_pos, hist_pos)

    def test_professor_memory_empty_not_injected(self) -> None:
        prompt = self._build("Riggs", professor_memory="")
        self.assertNotIn("Memory:", prompt)

    def test_willow_context_injected(self) -> None:
        prompt = self._build("Riggs", willow_context="### Willow Knows:\n- atom one")
        self.assertIn("Willow Knows", prompt)
        self.assertIn("atom one", prompt)

    def test_willow_context_appears_after_memory_before_history(self) -> None:
        history = [{"role": "user", "content": "test"}]
        prompt = self._build(
            "Riggs", history,
            professor_memory="memory content",
            willow_context="### Willow Knows:\n- atom",
        )
        mem_pos = prompt.index("memory content")
        willow_pos = prompt.index("Willow Knows")
        hist_pos = prompt.index("### Conversation History:")
        self.assertLess(mem_pos, willow_pos)
        self.assertLess(willow_pos, hist_pos)

    def test_willow_context_empty_not_injected(self) -> None:
        prompt = self._build("Riggs", willow_context="")
        self.assertNotIn("Willow Knows", prompt)

    def test_no_duplicate_user_message(self) -> None:
        history = [{"role": "user", "content": "measure this"}]
        prompt = self._build("Riggs", history)
        self.assertEqual(prompt.count("measure this"), 1)

    # ── course context ────────────────────────────────────────────────────────

    def test_course_context_injected(self) -> None:
        with mock.patch.object(consult_engine, "_load_catalog", return_value=_MINIMAL_CATALOG):
            prompt = self._build("Riggs", course_code="MECH 101")
        self.assertIn("Measurement Fundamentals", prompt)
        self.assertIn("MECH 101", prompt)

    def test_unknown_course_code_no_crash(self) -> None:
        with mock.patch.object(consult_engine, "_load_catalog", return_value=_MINIMAL_CATALOG):
            prompt = self._build("Riggs", course_code="MECH 999")
        self.assertIn("You are Riggs.", prompt)


class FormatResponsePlainTests(unittest.TestCase):
    def _fmt(self, professor, content, category=""):
        return consult_engine.format_response_plain(professor, content, category)

    def test_empty_content_returns_empty(self) -> None:
        self.assertEqual(self._fmt("Willow", ""), "")
        self.assertEqual(self._fmt("Willow", "   "), "")

    def test_default_fallthrough(self) -> None:
        result = self._fmt("Willow", "hello there")
        self.assertEqual(result, "hello there")

    # ── Gerald ────────────────────────────────────────────────────────────────

    def test_gerald_napkin_box(self) -> None:
        result = self._fmt("Gerald", "Yes.")
        self.assertIn("napkin", result)
        self.assertIn("╔", result)
        self.assertIn("╚", result)
        self.assertIn("— G.", result)

    def test_gerald_truncates_at_300(self) -> None:
        long_text = "A" * 400
        result = self._fmt("Gerald", long_text)
        self.assertIn("*confetti*", result)
        lines = [l for l in result.splitlines() if "A" in l]
        content = "".join(lines)
        self.assertLessEqual(len(content.replace(" ", "")), 310)

    def test_gerald_short_text_no_confetti(self) -> None:
        result = self._fmt("Gerald", "CYCLE COMPLETE.")
        self.assertNotIn("*confetti*", result)

    # ── Copenhagen ────────────────────────────────────────────────────────────

    def test_copenhagen_has_orange_and_hanz(self) -> None:
        result = self._fmt("Copenhagen", "Winter is nice.")
        self.assertIn("🍊", result)
        self.assertIn("Hanz translates", result)
        self.assertIn("Winter is nice.", result)

    # ── Steve ────────────────────────────────────────────────────────────────

    def test_steve_has_hotdog_header_and_dog_tag(self) -> None:
        result = self._fmt("Steve", "Hello!")
        self.assertIn("🌭", result)
        self.assertIn("[Dog", result)
        self.assertIn("of 10]", result)

    # ── Oakenscroll ───────────────────────────────────────────────────────────

    def test_oakenscroll_strips_asterisk_emphasis(self) -> None:
        result = self._fmt("Oakenscroll", "This is *important* and *correct*.")
        self.assertNotIn("*", result)
        self.assertIn("important", result)

    # ── Riggs ─────────────────────────────────────────────────────────────────

    def test_riggs_converts_emphasis_to_brackets(self) -> None:
        result = self._fmt("Riggs", "We *measure* this.")
        self.assertIn("[measure]", result)
        self.assertNotIn("*", result)

    # ── Ofshield ─────────────────────────────────────────────────────────────

    def test_ofshield_noted_prefix(self) -> None:
        result = self._fmt("Ofshield", "Passage noted.")
        self.assertTrue(result.startswith("*noted*"))

    # ── Binder ───────────────────────────────────────────────────────────────

    def test_binder_filed_under_default(self) -> None:
        result = self._fmt("Binder", "All filed.")
        self.assertIn("[Filed under: general correspondence]", result)

    def test_binder_filed_under_llm_category(self) -> None:
        result = self._fmt("Binder", "All filed.", category="student grievance")
        self.assertIn("[Filed under: student grievance]", result)
        self.assertNotIn("general correspondence", result)

    # ── Pigeon ────────────────────────────────────────────────────────────────

    def test_pigeon_prefix(self) -> None:
        result = self._fmt("Pigeon", "I know the way!")
        self.assertIn("🐦 PIGEON:", result)
        self.assertIn("I know the way!", result)


class ConsultFunctionTests(unittest.TestCase):
    """Integration-style tests for consult() with mocked LLM."""

    def _mock_ask(self, text="Hello, friend. Copenhagen sits quietly."):
        return mock.patch.object(
            consult_engine.tui_llm,
            "ask",
            return_value={"ok": True, "text": text, "provider": "llama3.1:8b", "tier": "ollama"},
        )

    def test_consult_returns_ok(self) -> None:
        with self._mock_ask():
            result = consult_engine.consult(professor="Willow", message="hello")
        self.assertTrue(result["ok"])
        self.assertIn("text", result)

    def test_consult_propagates_llm_failure(self) -> None:
        with mock.patch.object(
            consult_engine.tui_llm,
            "ask",
            return_value={"ok": False, "error": "timeout", "tier": "ollama"},
        ):
            result = consult_engine.consult(professor="Willow", message="hello")
        self.assertFalse(result["ok"])

    def test_consult_binder_calls_categorize(self) -> None:
        with self._mock_ask("All filed."), mock.patch.object(
            consult_engine.tui_llm,
            "categorize_for_binder",
            return_value="academic inquiry",
        ) as mock_cat:
            result = consult_engine.consult(professor="Binder", message="grade appeal")
        mock_cat.assert_called_once_with("grade appeal")
        self.assertIn("academic inquiry", result["text"])

    def test_consult_non_binder_skips_categorize(self) -> None:
        with self._mock_ask(), mock.patch.object(
            consult_engine.tui_llm, "categorize_for_binder"
        ) as mock_cat:
            consult_engine.consult(professor="Riggs", message="measure this")
        mock_cat.assert_not_called()

    def test_consult_history_passed_through(self) -> None:
        history = [{"role": "user", "content": "prior msg"}]
        with self._mock_ask() as mock_ask:
            consult_engine.consult(professor="Willow", message="follow up", history=history)
        call_args = mock_ask.call_args
        prompt_arg = call_args[0][0]
        self.assertIn("prior msg", prompt_arg)
        self.assertIn("follow up", prompt_arg)


if __name__ == "__main__":
    unittest.main()
