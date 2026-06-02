"""Tests for Nest commit manifest writing."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import commit_package


class CommitPackageTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self.nest = Path(self._tmpdir) / "nest"
        self.nest.mkdir()
        (self.nest / "coparent.db").write_bytes(b"sqlite")
        (self.nest / "coparent_db_export.json").write_text("{}", encoding="utf-8")

        self._patch_nest = mock.patch.object(commit_package, "NEST", self.nest)
        self._patch_nest.start()

    def tearDown(self) -> None:
        self._patch_nest.stop()
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_find_artifacts(self) -> None:
        files = commit_package.find_artifacts(self.nest)
        self.assertIn("coparent.db", files)
        self.assertIn("coparent_db_export.json", files)

    def test_write_commit_manifest_dry_run(self) -> None:
        result = commit_package.write_commit_manifest(
            summary="Test session",
            session_date="2026-06-01",
            nest=self.nest,
            dry_run=True,
        )
        self.assertTrue(result["ok"])
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["manifest"]["kind"], "law_gazelle_commit")
        self.assertNotIn("legal_commit_2026-06-01.json", list(self.nest.iterdir()))

    def test_write_commit_manifest_writes_file(self) -> None:
        result = commit_package.write_commit_manifest(
            summary="Atoms updated",
            session_date="2026-06-01",
            nest=self.nest,
        )
        self.assertTrue(result["ok"])
        path = Path(result["path"])
        self.assertTrue(path.exists())
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["summary"], "Atoms updated")
        self.assertEqual(data["session_date"], "2026-06-01")

    def test_write_commit_manifest_missing_nest(self) -> None:
        result = commit_package.write_commit_manifest(nest="/nonexistent/nest/path")
        self.assertFalse(result["ok"])
        self.assertIn("error", result)

    def test_find_artifacts_includes_drafts(self) -> None:
        drafts = self.nest / "drafts"
        drafts.mkdir()
        (drafts / "Campbell_schedule.md").write_text("# Draft", encoding="utf-8")
        files = commit_package.find_artifacts(self.nest)
        self.assertIn("drafts/Campbell_schedule.md", files)

    def test_read_latest_manifest(self) -> None:
        self.assertIsNone(commit_package.read_latest_manifest(self.nest))
        commit_package.write_commit_manifest(
            summary="First commit",
            session_date="2026-05-30",
            nest=self.nest,
        )
        latest = commit_package.read_latest_manifest(self.nest)
        self.assertIsNotNone(latest)
        assert latest is not None
        self.assertEqual(latest["summary"], "First commit")
        self.assertEqual(latest["session_date"], "2026-05-30")
        self.assertGreaterEqual(latest["file_count"], 2)

    def test_gazelle_mcp_dispatch(self) -> None:
        import gazelle_mcp

        result = gazelle_mcp._dispatch(
            "gazelle_commit",
            {"summary": "MCP test", "session_date": "2026-06-01", "dry_run": True},
        )
        self.assertTrue(result["ok"])
        self.assertTrue(result["dry_run"])

    def test_gazelle_mcp_dispatch_ai_inspect_fact(self) -> None:
        import gazelle_mcp

        fact_row = {"atom_id": "ATM-001", "fact": "Thursday exchange"}
        with mock.patch(
            "gazelle_mcp.intelligence.inspect_fact_row",
            return_value={"ok": True, "atom_id": "ATM-001", "text": "review"},
        ) as inspect_fact:
            result = gazelle_mcp._dispatch(
                "gazelle_ai_inspect_fact",
                {"fact_row": fact_row},
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["atom_id"], "ATM-001")
        inspect_fact.assert_called_once_with(fact_row)


if __name__ == "__main__":
    unittest.main()
