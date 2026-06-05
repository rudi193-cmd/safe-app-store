"""Tests for chat_engine.ChatSession — persistence wiring and session lifecycle."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent))

import chat_engine


def _make_session(professor="Riggs", session_id="test-001"):
    with mock.patch.object(chat_engine, "_DB_AVAILABLE", False):
        return chat_engine.ChatSession(professor, session_id)


def _fleet_ok(text="Measure twice."):
    """Patch _fleet_ask to return a successful response object."""
    class _R:
        content = text
        provider = "llama3.1:8b"

    def _fake_ask(prompt, tier="free"):
        return _R()

    return mock.patch.object(chat_engine, "_fleet_ask", side_effect=_fake_ask)


# ---------------------------------------------------------------------------
# Basic session behaviour (no DB)
# ---------------------------------------------------------------------------

class ChatSessionBasicTests(unittest.TestCase):
    def test_professor_name_stored(self) -> None:
        session = _make_session("Willow")
        self.assertEqual(session.professor_name, "Willow")

    def test_history_starts_empty(self) -> None:
        session = _make_session()
        self.assertEqual(session.history, [])

    def test_send_message_appends_to_history(self) -> None:
        session = _make_session()
        with _fleet_ok():
            session.send_message("hello")
        self.assertEqual(len(session.history), 2)
        self.assertEqual(session.history[0]["role"], "user")
        self.assertEqual(session.history[1]["role"], "assistant")

    def test_send_message_returns_reply(self) -> None:
        session = _make_session()
        with _fleet_ok("Measure twice."):
            reply = session.send_message("hi")
        self.assertEqual(reply, "Measure twice.")

    def test_clear_history_empties_history(self) -> None:
        session = _make_session()
        with _fleet_ok():
            session.send_message("hi")
        session.clear_history()
        self.assertEqual(session.history, [])

    def test_get_history_returns_history(self) -> None:
        session = _make_session()
        with _fleet_ok():
            session.send_message("hi")
        self.assertIs(session.get_history(), session.history)

    def test_fleet_unavailable_returns_fallback(self) -> None:
        session = _make_session()
        with mock.patch.object(chat_engine, "_fleet_ask", return_value=None):
            reply = session.send_message("hi")
        self.assertIn("unavailable", reply.lower())

    def test_export_contains_professor_name(self) -> None:
        session = _make_session("Riggs")
        with _fleet_ok():
            session.send_message("hello")
        export = session.export_conversation()
        self.assertIn("Riggs", export)


# ---------------------------------------------------------------------------
# Persistence wiring
# ---------------------------------------------------------------------------

class ChatSessionPersistenceTests(unittest.TestCase):
    def _make_db_mock(self, session_id=42):
        """Return a mock chat_db module and a context manager that installs it."""
        db = mock.MagicMock()
        db.get_connection.return_value = mock.MagicMock()
        db.add_session.return_value = {"id": session_id}
        db.add_message.return_value = {}
        return db

    def _make_db_session(self, professor="Riggs", db=None):
        db = db or self._make_db_mock()
        with mock.patch.object(chat_engine, "_DB_AVAILABLE", True), \
             mock.patch.object(chat_engine, "_chat_db", db):
            session = chat_engine.ChatSession(professor, "test-db-001")
        return session, db

    def test_add_session_called_on_init(self) -> None:
        session, db = self._make_db_session()
        db.add_session.assert_called_once()
        call_kwargs = db.add_session.call_args[1]
        self.assertEqual(call_kwargs["faculty_member"], "Riggs")

    def test_db_session_id_stored(self) -> None:
        session, _ = self._make_db_session()
        self.assertEqual(session._db_session_id, 42)

    def test_add_message_called_on_send(self) -> None:
        session, db = self._make_db_session()
        with _fleet_ok("response text"), \
             mock.patch.object(chat_engine, "_DB_AVAILABLE", True), \
             mock.patch.object(chat_engine, "_chat_db", db):
            session.send_message("student question")
        self.assertEqual(db.add_message.call_count, 2)

    def test_user_message_written_first(self) -> None:
        session, db = self._make_db_session()
        with _fleet_ok(), \
             mock.patch.object(chat_engine, "_DB_AVAILABLE", True), \
             mock.patch.object(chat_engine, "_chat_db", db):
            session.send_message("the question")
        first_call = db.add_message.call_args_list[0][1]
        self.assertEqual(first_call["role"], "user")
        self.assertEqual(first_call["content"], "the question")

    def test_assistant_message_written_second(self) -> None:
        session, db = self._make_db_session()
        with _fleet_ok("the answer"), \
             mock.patch.object(chat_engine, "_DB_AVAILABLE", True), \
             mock.patch.object(chat_engine, "_chat_db", db):
            session.send_message("question")
        second_call = db.add_message.call_args_list[1][1]
        self.assertEqual(second_call["role"], "assistant")
        self.assertEqual(second_call["content"], "the answer")

    def test_db_failure_on_init_does_not_crash(self) -> None:
        db = self._make_db_mock()
        db.get_connection.side_effect = Exception("connection refused")
        with mock.patch.object(chat_engine, "_DB_AVAILABLE", True), \
             mock.patch.object(chat_engine, "_chat_db", db):
            session = chat_engine.ChatSession("Riggs", "fail-001")
        self.assertIsNone(session._db_session_id)

    def test_db_failure_on_send_does_not_crash(self) -> None:
        session, db = self._make_db_session()
        db.get_connection.side_effect = Exception("write failed")
        with _fleet_ok(), \
             mock.patch.object(chat_engine, "_DB_AVAILABLE", True), \
             mock.patch.object(chat_engine, "_chat_db", db):
            reply = session.send_message("hi")
        self.assertEqual(reply, "Measure twice.")

    def test_no_db_available_skips_writes(self) -> None:
        session = _make_session()
        self.assertIsNone(session._db_session_id)
        db = self._make_db_mock()
        with _fleet_ok(), \
             mock.patch.object(chat_engine, "_DB_AVAILABLE", False), \
             mock.patch.object(chat_engine, "_chat_db", db):
            session.send_message("hi")
        db.add_message.assert_not_called()


if __name__ == "__main__":
    unittest.main()
