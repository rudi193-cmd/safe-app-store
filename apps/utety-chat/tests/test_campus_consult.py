"""Tests for campus_consult.py — JSON sidecar for Ratatui consultation chamber."""

from __future__ import annotations

import io
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent))

import campus_consult


def _run(stdin_data: str) -> tuple[dict | None, int]:
    """Run campus_consult.main() with the given stdin string.

    Returns (parsed_stdout_json_or_None, return_code).
    """
    captured = io.StringIO()
    with mock.patch("sys.stdin", io.StringIO(stdin_data)), \
         mock.patch("sys.stdout", captured):
        rc = campus_consult.main()
    output = captured.getvalue().strip()
    try:
        return json.loads(output), rc
    except json.JSONDecodeError:
        return None, rc


_OK_RESULT = {"ok": True, "text": "Measure twice.", "provider": "llama3.1:8b", "tier": "ollama"}
_FAIL_RESULT = {"ok": False, "error": "timeout", "tier": "ollama"}


class ValidRequestTests(unittest.TestCase):
    def _consult_mock(self, result=None):
        return mock.patch(
            "campus_consult.consult",
            return_value=result or _OK_RESULT,
        )

    def test_valid_request_returns_ok(self) -> None:
        with self._consult_mock():
            result, rc = _run('{"professor": "Riggs", "message": "hello"}')
        self.assertTrue(result["ok"])
        self.assertEqual(rc, 0)

    def test_professor_and_message_forwarded(self) -> None:
        with self._consult_mock() as m:
            _run('{"professor": "Willow", "message": "what is UTETY?"}')
        call_kwargs = m.call_args[1]
        self.assertEqual(call_kwargs["professor"], "Willow")
        self.assertEqual(call_kwargs["message"], "what is UTETY?")

    def test_compact_defaults_to_true(self) -> None:
        with self._consult_mock() as m:
            _run('{"professor": "Riggs", "message": "hi"}')
        self.assertTrue(m.call_args[1]["compact"])

    def test_compact_can_be_overridden(self) -> None:
        with self._consult_mock() as m:
            _run('{"professor": "Riggs", "message": "hi", "compact": false}')
        self.assertFalse(m.call_args[1]["compact"])

    def test_history_forwarded(self) -> None:
        payload = json.dumps({
            "professor": "Riggs",
            "message": "follow up",
            "history": [{"role": "user", "content": "prior"}],
        })
        with self._consult_mock() as m:
            _run(payload)
        self.assertEqual(m.call_args[1]["history"], [{"role": "user", "content": "prior"}])

    def test_course_code_forwarded(self) -> None:
        payload = json.dumps({
            "professor": "Riggs",
            "message": "lesson?",
            "course_code": "MECH 101",
        })
        with self._consult_mock() as m:
            _run(payload)
        self.assertEqual(m.call_args[1]["course_code"], "MECH 101")

    def test_missing_professor_defaults_to_willow(self) -> None:
        with self._consult_mock() as m:
            _run('{"message": "hello"}')
        self.assertEqual(m.call_args[1]["professor"], "Willow")

    def test_failure_result_forwarded(self) -> None:
        with self._consult_mock(_FAIL_RESULT):
            result, rc = _run('{"professor": "Riggs", "message": "hi"}')
        self.assertFalse(result["ok"])
        self.assertEqual(rc, 1)

    def test_output_is_valid_json(self) -> None:
        with self._consult_mock():
            result, _ = _run('{"professor": "Riggs", "message": "hi"}')
        self.assertIsNotNone(result)


class ErrorHandlingTests(unittest.TestCase):
    def test_invalid_json_returns_error(self) -> None:
        result, rc = _run("not json at all")
        self.assertIsNotNone(result)
        self.assertFalse(result["ok"])
        self.assertIn("invalid json", result["error"])
        self.assertEqual(rc, 1)

    def test_empty_message_returns_error(self) -> None:
        result, rc = _run('{"professor": "Riggs", "message": ""}')
        self.assertFalse(result["ok"])
        self.assertEqual(rc, 1)

    def test_whitespace_only_message_returns_error(self) -> None:
        result, rc = _run('{"professor": "Riggs", "message": "   "}')
        self.assertFalse(result["ok"])
        self.assertEqual(rc, 1)

    def test_missing_message_field_returns_error(self) -> None:
        result, rc = _run('{"professor": "Riggs"}')
        self.assertFalse(result["ok"])
        self.assertEqual(rc, 1)

    def test_empty_object_returns_error(self) -> None:
        result, rc = _run("{}")
        self.assertFalse(result["ok"])
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
