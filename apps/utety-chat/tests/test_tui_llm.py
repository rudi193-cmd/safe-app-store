"""Tests for layered LLM routing in tui_llm (all Ollama calls mocked)."""

from __future__ import annotations

import json
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

import tui_llm


def _make_ollama_response(text: str) -> mock.Mock:
    body = json.dumps({"response": text}).encode()
    resp = mock.MagicMock()
    resp.read.return_value = body
    resp.__enter__ = lambda s: s
    resp.__exit__ = mock.Mock(return_value=False)
    return resp


class AskOllamaTests(unittest.TestCase):
    def _patch_urlopen(self, response=None, side_effect=None):
        if side_effect:
            return mock.patch("urllib.request.urlopen", side_effect=side_effect)
        return mock.patch("urllib.request.urlopen", return_value=response)

    def test_success(self) -> None:
        with self._patch_urlopen(_make_ollama_response("hello there")):
            result = tui_llm._ask_ollama("prompt", model="llama3.1:8b")
        self.assertTrue(result["ok"])
        self.assertEqual(result["text"], "hello there")
        self.assertEqual(result["provider"], "llama3.1:8b")
        self.assertEqual(result["tier"], "ollama")

    def test_empty_response_is_not_ok(self) -> None:
        with self._patch_urlopen(_make_ollama_response("   ")):
            result = tui_llm._ask_ollama("prompt")
        self.assertFalse(result["ok"])
        self.assertIn("empty", result["error"])

    def test_url_error_returns_not_ok(self) -> None:
        with self._patch_urlopen(side_effect=urllib.error.URLError("connection refused")):
            result = tui_llm._ask_ollama("prompt")
        self.assertFalse(result["ok"])
        self.assertEqual(result["tier"], "ollama")

    def test_timeout_returns_not_ok(self) -> None:
        with self._patch_urlopen(side_effect=TimeoutError("timed out")):
            result = tui_llm._ask_ollama("prompt")
        self.assertFalse(result["ok"])

    def test_uses_correct_model_in_payload(self) -> None:
        captured = {}

        def fake_urlopen(req, timeout):
            captured["payload"] = json.loads(req.data)
            return _make_ollama_response("ok")

        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            tui_llm._ask_ollama("test prompt", model="llama3.2:3b")

        self.assertEqual(captured["payload"]["model"], "llama3.2:3b")
        self.assertEqual(captured["payload"]["prompt"], "test prompt")
        self.assertFalse(captured["payload"]["stream"])


class AskTests(unittest.TestCase):
    """Test the top-level ask() fallback chain."""

    def _patch_ollama(self, ok=True, text="response"):
        result = {"ok": ok, "text": text, "provider": "llama3.1:8b", "tier": "ollama"}
        if not ok:
            result = {"ok": False, "error": "fail", "tier": "ollama"}
        return mock.patch.object(tui_llm, "_ask_ollama", return_value=result)

    def _patch_willow(self, tier, ok=True):
        result = {"ok": ok, "text": "willow response", "provider": tier, "tier": tier}
        if not ok:
            result = {"ok": False, "error": "willow fail", "tier": tier}
        return mock.patch.object(tui_llm, "_ask_willow", return_value=result)

    def test_ollama_success_skips_willow(self) -> None:
        with self._patch_ollama(ok=True) as mock_ollama, \
             mock.patch.object(tui_llm, "_ask_willow") as mock_willow:
            result = tui_llm.ask("prompt")
        self.assertTrue(result["ok"])
        mock_willow.assert_not_called()

    def test_ollama_fail_falls_through_to_willow_free(self) -> None:
        willow_results = [
            {"ok": True, "text": "free tier", "provider": "free", "tier": "free"}
        ]
        with self._patch_ollama(ok=False), \
             mock.patch.object(tui_llm, "_ask_willow", side_effect=willow_results):
            result = tui_llm.ask("prompt")
        self.assertTrue(result["ok"])
        self.assertEqual(result["tier"], "free")

    def test_all_tiers_fail_returns_last_error(self) -> None:
        fail = {"ok": False, "error": "fail", "tier": "paid"}
        with self._patch_ollama(ok=False), \
             mock.patch.object(tui_llm, "_ask_willow", return_value=fail):
            result = tui_llm.ask("prompt")
        self.assertFalse(result["ok"])

    def test_gerald_uses_1b_model(self) -> None:
        captured = {}

        def fake_ollama(prompt, model):
            captured["model"] = model
            return {"ok": True, "text": "yes", "provider": model, "tier": "ollama"}

        with mock.patch.object(tui_llm, "_ask_ollama", side_effect=fake_ollama):
            tui_llm.ask("prompt", professor="Gerald")

        self.assertEqual(captured["model"], tui_llm.PROFESSOR_MODELS["Gerald"])

    def test_non_gerald_uses_default_model(self) -> None:
        captured = {}

        def fake_ollama(prompt, model):
            captured["model"] = model
            return {"ok": True, "text": "yes", "provider": model, "tier": "ollama"}

        with mock.patch.object(tui_llm, "_ask_ollama", side_effect=fake_ollama):
            tui_llm.ask("prompt", professor="Riggs")

        self.assertEqual(captured["model"], tui_llm.DEFAULT_MODEL)


class CategorizeBinder(unittest.TestCase):
    """Tests for Binder's LLM filing categorization."""

    def _patch_ollama(self, response_text):
        resp = {"ok": True, "text": response_text, "provider": "llama3.2:3b", "tier": "ollama"}
        return mock.patch.object(tui_llm, "_ask_ollama", return_value=resp)

    def test_recognizes_known_category(self) -> None:
        with self._patch_ollama("student grievance"):
            cat = tui_llm.categorize_for_binder("Professor never shows up")
        self.assertEqual(cat, "student grievance")

    def test_recognizes_category_case_insensitive(self) -> None:
        with self._patch_ollama("Academic Inquiry"):
            cat = tui_llm.categorize_for_binder("question about curriculum")
        self.assertEqual(cat, "academic inquiry")

    def test_strips_quotes_from_response(self) -> None:
        with self._patch_ollama('"general correspondence"'):
            cat = tui_llm.categorize_for_binder("just saying hi")
        self.assertEqual(cat, "general correspondence")

    def test_strips_trailing_period(self) -> None:
        with self._patch_ollama("administrative matter."):
            cat = tui_llm.categorize_for_binder("some admin thing")
        self.assertEqual(cat, "administrative matter")

    def test_unrecognized_response_falls_back(self) -> None:
        with self._patch_ollama("I cannot determine this"):
            cat = tui_llm.categorize_for_binder("something weird")
        self.assertEqual(cat, "general correspondence")

    def test_ollama_failure_falls_back(self) -> None:
        fail = {"ok": False, "error": "timeout", "tier": "ollama"}
        with mock.patch.object(tui_llm, "_ask_ollama", return_value=fail):
            cat = tui_llm.categorize_for_binder("anything")
        self.assertEqual(cat, "general correspondence")

    def test_all_categories_recognized(self) -> None:
        for cat in tui_llm._BINDER_CATEGORIES:
            with self._patch_ollama(cat):
                result = tui_llm.categorize_for_binder("test message")
            self.assertEqual(result, cat, f"failed to recognize category: {cat!r}")

    def test_message_truncated_to_300_chars(self) -> None:
        captured = {}

        def fake_ollama(prompt, model):
            captured["prompt"] = prompt
            return {"ok": True, "text": "general correspondence", "tier": "ollama",
                    "provider": model}

        long_msg = "X" * 600
        with mock.patch.object(tui_llm, "_ask_ollama", side_effect=fake_ollama):
            tui_llm.categorize_for_binder(long_msg)

        # 300-char truncation should appear in the prompt
        self.assertIn("X" * 300, captured["prompt"])
        self.assertNotIn("X" * 301, captured["prompt"])


if __name__ == "__main__":
    unittest.main()
