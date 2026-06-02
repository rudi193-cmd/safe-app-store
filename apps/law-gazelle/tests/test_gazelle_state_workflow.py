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


if __name__ == "__main__":
    unittest.main()
