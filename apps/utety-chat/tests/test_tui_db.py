"""Tests for per-professor SQLite session persistence."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

import tui_db


class TuiDbTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self._db_dir = Path(self._tmpdir) / "sessions"
        self._patch = mock.patch.object(tui_db, "_DB_DIR", self._db_dir)
        self._patch.start()

    def tearDown(self) -> None:
        self._patch.stop()
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    # ── basic CRUD ────────────────────────────────────────────────────────────

    def test_save_and_load_roundtrip(self) -> None:
        tui_db.save_message("Willow", "user", "hello")
        tui_db.save_message("Willow", "assistant", "hi there", provider="llama3.1:8b")
        history = tui_db.load_history("Willow")
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["role"], "user")
        self.assertEqual(history[0]["content"], "hello")
        self.assertEqual(history[1]["role"], "assistant")
        self.assertEqual(history[1]["provider"], "llama3.1:8b")

    def test_load_empty_professor(self) -> None:
        history = tui_db.load_history("Nova")
        self.assertEqual(history, [])

    def test_professors_are_isolated(self) -> None:
        tui_db.save_message("Riggs", "user", "measure this")
        tui_db.save_message("Ada", "user", "uptime check")
        self.assertEqual(len(tui_db.load_history("Riggs")), 1)
        self.assertEqual(len(tui_db.load_history("Ada")), 1)
        self.assertEqual(tui_db.load_history("Riggs")[0]["content"], "measure this")

    def test_clear_history(self) -> None:
        tui_db.save_message("Gerald", "user", "napkin")
        tui_db.save_message("Gerald", "assistant", "*rotates*")
        tui_db.clear_history("Gerald")
        self.assertEqual(tui_db.load_history("Gerald"), [])

    def test_clear_does_not_affect_other_professors(self) -> None:
        tui_db.save_message("Steve", "user", "hot dog")
        tui_db.save_message("Binder", "user", "file this")
        tui_db.clear_history("Steve")
        self.assertEqual(tui_db.load_history("Binder")[0]["content"], "file this")

    def test_message_count(self) -> None:
        self.assertEqual(tui_db.message_count("Oakenscroll"), 0)
        tui_db.save_message("Oakenscroll", "user", "q1")
        tui_db.save_message("Oakenscroll", "assistant", "a1")
        self.assertEqual(tui_db.message_count("Oakenscroll"), 2)

    # ── meta table ────────────────────────────────────────────────────────────

    def test_meta_get_default(self) -> None:
        self.assertEqual(tui_db.get_meta("Oakenscroll", "filed_count", "0"), "0")

    def test_meta_set_and_get(self) -> None:
        tui_db.set_meta("Oakenscroll", "filed_count", "7")
        self.assertEqual(tui_db.get_meta("Oakenscroll", "filed_count"), "7")

    def test_meta_upsert(self) -> None:
        tui_db.set_meta("Oakenscroll", "filed_count", "3")
        tui_db.set_meta("Oakenscroll", "filed_count", "9")
        self.assertEqual(tui_db.get_meta("Oakenscroll", "filed_count"), "9")

    def test_meta_isolated_per_professor(self) -> None:
        tui_db.set_meta("Oakenscroll", "filed_count", "5")
        tui_db.set_meta("Binder", "filed_count", "12")
        self.assertEqual(tui_db.get_meta("Oakenscroll", "filed_count"), "5")
        self.assertEqual(tui_db.get_meta("Binder", "filed_count"), "12")

    # ── export ────────────────────────────────────────────────────────────────

    def test_export_markdown_empty(self) -> None:
        md = tui_db.export_markdown("Jeles")
        self.assertIn("Jeles", md)

    def test_export_markdown_structure(self) -> None:
        tui_db.save_message("Jeles", "user", "catalog query")
        tui_db.save_message("Jeles", "assistant", "found it")
        md = tui_db.export_markdown("Jeles")
        self.assertIn("**You**", md)
        self.assertIn("**Jeles**", md)
        self.assertIn("catalog query", md)
        self.assertIn("found it", md)

    # ── slug / db path ────────────────────────────────────────────────────────

    def test_db_files_created_in_db_dir(self) -> None:
        tui_db.save_message("Hanz", "user", "hello friend")
        self.assertTrue((self._db_dir / "hanz.db").exists())

    def test_professor_with_space_in_name(self) -> None:
        tui_db.save_message("Grandma Oracle", "user", "tell me")
        self.assertTrue((self._db_dir / "grandma_oracle.db").exists())
        self.assertEqual(len(tui_db.load_history("Grandma Oracle")), 1)


if __name__ == "__main__":
    unittest.main()
