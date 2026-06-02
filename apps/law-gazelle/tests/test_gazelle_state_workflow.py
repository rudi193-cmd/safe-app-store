"""Tests for workflow sidecar tables (activity, fact verification)."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import gazelle_state


class GazelleStateWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self.app_data = Path(self._tmpdir) / "app"
        self.app_data.mkdir()
        self._patches = [
            mock.patch.object(gazelle_state, "APP_DATA", self.app_data),
            mock.patch.object(gazelle_state, "STATE_DB", self.app_data / "gazelle_state.db"),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self) -> None:
        for p in self._patches:
            p.stop()
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_log_activity_and_list(self) -> None:
        gazelle_state.log_activity("note", "Test note added", source_db="coparent", item_type="atom", item_id="ATM-001")
        events = gazelle_state.list_activity(limit=5)
        self.assertGreaterEqual(len(events), 1)
        self.assertEqual(events[0]["event_type"], "note")

    def test_fact_verification_roundtrip(self) -> None:
        gazelle_state.set_fact_verification("coparent", "atom", "ATM-001", "verified")
        self.assertEqual(
            gazelle_state.get_fact_verification("coparent", "atom", "ATM-001"),
            "verified",
        )
        gazelle_state.set_fact_verification("coparent", "atom", "ATM-001", "needs_source")
        self.assertEqual(
            gazelle_state.get_fact_verification("coparent", "atom", "ATM-001"),
            "needs_source",
        )

    def test_matter_stage(self) -> None:
        gazelle_state.set_matter_stage("coparent", "Schedule Response")
        self.assertEqual(gazelle_state.get_matter_stage("coparent"), "Schedule Response")

    def test_mark_resolved_logs_activity(self) -> None:
        gazelle_state.mark_resolved("coparent", "atom", "ATM-099")
        types = [e["event_type"] for e in gazelle_state.list_activity(limit=10)]
        self.assertIn("resolved", types)

    def test_ai_cache_roundtrip_and_verification_clears_inspect(self) -> None:
        key = gazelle_state.ai_cache_key("ai_fact_inspect", "coparent:ATM-010")
        fp = "abc123"
        gazelle_state.put_ai_cache(
            key,
            "ai_fact_inspect",
            "cached body",
            fingerprint=fp,
            source_db="coparent",
            item_type="atom",
            item_id="ATM-010",
        )
        hit = gazelle_state.get_ai_cache(key, fingerprint=fp)
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit["body"], "cached body")

        gazelle_state.set_fact_verification("coparent", "atom", "ATM-010", "verified")
        miss = gazelle_state.get_ai_cache(
            key, fingerprint=gazelle_state.fingerprint_payload({"verification": "verified"})
        )
        self.assertIsNone(miss)
        cleared = gazelle_state.get_ai_cache(key)
        self.assertIsNone(cleared)

    def test_ai_cache_expires_at_set(self) -> None:
        key = gazelle_state.ai_cache_key("ai_brief", "card:X")
        gazelle_state.put_ai_cache(key, "ai_brief", "body", fingerprint="fp1")
        import sqlite3
        with sqlite3.connect(gazelle_state.STATE_DB) as conn:
            row = conn.execute("SELECT expires_at FROM ai_cache WHERE cache_key=?", (key,)).fetchone()
        self.assertIsNotNone(row)
        self.assertIsNotNone(row[0])
        self.assertGreater(row[0], gazelle_state._now())

    def test_ai_cache_expired_returns_none(self) -> None:
        key = gazelle_state.ai_cache_key("ai_brief", "card:expired")
        gazelle_state.put_ai_cache(key, "ai_brief", "old body", fingerprint="fp2")
        import sqlite3
        with sqlite3.connect(gazelle_state.STATE_DB) as conn:
            conn.execute(
                "UPDATE ai_cache SET expires_at=? WHERE cache_key=?",
                ("2000-01-01T00:00:00Z", key),
            )
            conn.commit()
        result = gazelle_state.get_ai_cache(key, fingerprint="fp2")
        self.assertIsNone(result)

    def test_ai_cache_migration_adds_expires_at(self) -> None:
        import sqlite3
        # Simulate an old DB without expires_at column
        with sqlite3.connect(gazelle_state.STATE_DB) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ai_cache (
                    cache_key TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    source_db TEXT,
                    item_type TEXT,
                    item_id TEXT,
                    body TEXT NOT NULL,
                    model TEXT,
                    input_fingerprint TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.commit()
        # _connect() should add the column via migration
        gazelle_state._connect().close()
        with sqlite3.connect(gazelle_state.STATE_DB) as conn:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(ai_cache)").fetchall()}
        self.assertIn("expires_at", cols)


if __name__ == "__main__":
    unittest.main()
