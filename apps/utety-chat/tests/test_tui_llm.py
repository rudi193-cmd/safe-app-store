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
    """Non-streaming response mock — supports resp.read()."""
    body = json.dumps({"response": text}).encode()
    resp = mock.MagicMock()
    resp.read.return_value = body
    resp.__enter__ = lambda s: s
    resp.__exit__ = mock.Mock(return_value=False)
    return resp


def _make_ollama_stream(tokens: list[str]) -> mock.Mock:
    """Streaming response mock — supports resp.readline() line-by-line."""
    lines = [
        json.dumps({"response": t, "done": False}).encode() + b"\n"
        for t in tokens
    ]
    lines.append(json.dumps({"response": "", "done": True}).encode() + b"\n")
    lines.append(b"")  # sentinel for readline loop termination

    iterator = iter(lines)

    resp = mock.MagicMock()
    resp.readline.side_effect = lambda: next(iterator, b"")
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

    # ── streaming ──────────────────────────────────────────────────────────────

    def test_streaming_calls_on_chunk_per_token(self) -> None:
        tokens = ["Hello", ", ", "friend", "."]
        received = []

        with mock.patch("urllib.request.urlopen", return_value=_make_ollama_stream(tokens)):
            tui_llm._ask_ollama("prompt", on_chunk=received.append)

        self.assertEqual(received, tokens)

    def test_streaming_accumulates_full_text(self) -> None:
        tokens = ["We ", "measure."]
        with mock.patch("urllib.request.urlopen", return_value=_make_ollama_stream(tokens)):
            result = tui_llm._ask_ollama("prompt", on_chunk=lambda t: None)
        self.assertTrue(result["ok"])
        self.assertEqual(result["text"], "We measure.")

    def test_streaming_payload_has_stream_true(self) -> None:
        captured = {}

        def fake_urlopen(req, timeout):
            captured["payload"] = json.loads(req.data)
            return _make_ollama_stream(["hi"])

        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            tui_llm._ask_ollama("prompt", on_chunk=lambda t: None)

        self.assertTrue(captured["payload"]["stream"])

    def test_streaming_empty_tokens_returns_not_ok(self) -> None:
        with mock.patch("urllib.request.urlopen", return_value=_make_ollama_stream([])):
            result = tui_llm._ask_ollama("prompt", on_chunk=lambda t: None)
        self.assertFalse(result["ok"])


class AskTests(unittest.TestCase):
    """Test the top-level ask() fallback chain."""

    def _patch_ollama(self, ok=True, text="response"):
        result = {"ok": ok, "text": text, "provider": "llama3.1:8b", "tier": "ollama"}
        if not ok:
            result = {"ok": False, "error": "fail", "tier": "ollama"}
        return mock.patch.object(tui_llm, "_ask_ollama", return_value=result)

    def _patch_groq(self, ok=True):
        result = {"ok": ok, "text": "groq response", "provider": tui_llm.GROQ_DEFAULT_MODEL, "tier": "groq"}
        if not ok:
            result = {"ok": False, "error": "groq fail", "tier": "groq"}
        return mock.patch.object(tui_llm, "_ask_groq", return_value=result)

    def test_ollama_success_skips_groq(self) -> None:
        with self._patch_ollama(ok=True), \
             mock.patch.object(tui_llm, "_ask_groq") as mock_groq:
            result = tui_llm.ask("prompt")
        self.assertTrue(result["ok"])
        mock_groq.assert_not_called()

    def test_ollama_fail_falls_through_to_groq(self) -> None:
        with self._patch_ollama(ok=False), self._patch_groq(ok=True):
            result = tui_llm.ask("prompt")
        self.assertTrue(result["ok"])
        self.assertEqual(result["tier"], "groq")

    def test_all_tiers_fail_returns_groq_error(self) -> None:
        with self._patch_ollama(ok=False), self._patch_groq(ok=False):
            result = tui_llm.ask("prompt")
        self.assertFalse(result["ok"])

    def test_gerald_uses_1b_model(self) -> None:
        captured = {}

        def fake_ollama(prompt, model, on_chunk=None):
            captured["model"] = model
            return {"ok": True, "text": "yes", "provider": model, "tier": "ollama"}

        with mock.patch.object(tui_llm, "_ask_ollama", side_effect=fake_ollama):
            tui_llm.ask("prompt", professor="Gerald")

        self.assertEqual(captured["model"], tui_llm.PROFESSOR_MODELS["Gerald"])

    def test_non_gerald_uses_default_model(self) -> None:
        captured = {}

        def fake_ollama(prompt, model, on_chunk=None):
            captured["model"] = model
            return {"ok": True, "text": "yes", "provider": model, "tier": "ollama"}

        with mock.patch.object(tui_llm, "_ask_ollama", side_effect=fake_ollama):
            tui_llm.ask("prompt", professor="Riggs")

        self.assertEqual(captured["model"], tui_llm.DEFAULT_MODEL)

    def test_on_chunk_forwarded_to_ollama(self) -> None:
        received = []

        def fake_ollama(prompt, model, on_chunk=None):
            if on_chunk:
                on_chunk("token")
            return {"ok": True, "text": "token", "provider": model, "tier": "ollama"}

        with mock.patch.object(tui_llm, "_ask_ollama", side_effect=fake_ollama):
            tui_llm.ask("prompt", on_chunk=received.append)

        self.assertEqual(received, ["token"])


class AskGroqTests(unittest.TestCase):
    """Tests for the Groq fallback tier."""

    def _make_groq_response(self, text: str) -> mock.Mock:
        body = json.dumps({
            "choices": [{"message": {"content": text}}]
        }).encode()
        resp = mock.MagicMock()
        resp.read.return_value = body
        resp.__enter__ = lambda s: s
        resp.__exit__ = mock.Mock(return_value=False)
        return resp

    def test_success_with_key(self) -> None:
        with mock.patch.dict("os.environ", {"GROQ_API_KEY": "test-key"}), \
             mock.patch("urllib.request.urlopen", return_value=self._make_groq_response("measure this")):
            result = tui_llm._ask_groq("prompt")
        self.assertTrue(result["ok"])
        self.assertEqual(result["text"], "measure this")
        self.assertEqual(result["tier"], "groq")

    def test_no_key_returns_error(self) -> None:
        with mock.patch.dict("os.environ", {}, clear=True):
            result = tui_llm._ask_groq("prompt")
        self.assertFalse(result["ok"])
        self.assertIn("GROQ_API_KEY", result["error"])

    def test_url_error_returns_not_ok(self) -> None:
        with mock.patch.dict("os.environ", {"GROQ_API_KEY": "test-key"}), \
             mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("timeout")):
            result = tui_llm._ask_groq("prompt")
        self.assertFalse(result["ok"])
        self.assertEqual(result["tier"], "groq")

    def test_uses_bearer_auth_header(self) -> None:
        captured = {}

        def fake_urlopen(req, timeout):
            captured["headers"] = req.headers
            return self._make_groq_response("hi")

        with mock.patch.dict("os.environ", {"GROQ_API_KEY": "my-secret-key"}), \
             mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            tui_llm._ask_groq("prompt")

        self.assertIn("Bearer my-secret-key", captured["headers"].get("Authorization", ""))

    def test_uses_groq_default_model(self) -> None:
        captured = {}

        def fake_urlopen(req, timeout):
            captured["payload"] = json.loads(req.data)
            return self._make_groq_response("hi")

        with mock.patch.dict("os.environ", {"GROQ_API_KEY": "key"}), \
             mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            tui_llm._ask_groq("prompt")

        self.assertEqual(captured["payload"]["model"], tui_llm.GROQ_DEFAULT_MODEL)

    def test_empty_response_returns_not_ok(self) -> None:
        with mock.patch.dict("os.environ", {"GROQ_API_KEY": "key"}), \
             mock.patch("urllib.request.urlopen", return_value=self._make_groq_response("   ")):
            result = tui_llm._ask_groq("prompt")
        self.assertFalse(result["ok"])


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

        def fake_ollama(prompt, model, on_chunk=None):
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
