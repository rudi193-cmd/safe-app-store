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
            session_date="2099-06-01",
            nest=self.nest,
            dry_run=True,
        )
        self.assertTrue(result["ok"])
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["manifest"]["kind"], "law_gazelle_commit")
        self.assertNotIn("legal_commit_2099-06-01.json", list(self.nest.iterdir()))

    def test_write_commit_manifest_writes_file(self) -> None:
        result = commit_package.write_commit_manifest(
            summary="Atoms updated",
            session_date="2099-06-01",
            nest=self.nest,
        )
        self.assertTrue(result["ok"])
        path = Path(result["path"])
        self.assertTrue(path.exists())
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["summary"], "Atoms updated")
        self.assertEqual(data["session_date"], "2099-06-01")

    def test_write_commit_manifest_missing_nest(self) -> None:
        result = commit_package.write_commit_manifest(nest="/nonexistent/nest/path")
        self.assertFalse(result["ok"])
        self.assertIn("error", result)

    def test_find_artifacts_includes_drafts(self) -> None:
        drafts = self.nest / "drafts"
        drafts.mkdir()
        (drafts / "CaseDraft_schedule.md").write_text("# Draft", encoding="utf-8")
        files = commit_package.find_artifacts(self.nest)
        self.assertIn("drafts/CaseDraft_schedule.md", files)

    def test_read_latest_manifest(self) -> None:
        self.assertIsNone(commit_package.read_latest_manifest(self.nest))
        commit_package.write_commit_manifest(
            summary="First commit",
            session_date="2099-05-30",
            nest=self.nest,
        )
        latest = commit_package.read_latest_manifest(self.nest)
        self.assertIsNotNone(latest)
        assert latest is not None
        self.assertEqual(latest["summary"], "First commit")
        self.assertEqual(latest["session_date"], "2099-05-30")
        self.assertGreaterEqual(latest["file_count"], 2)

    def test_gazelle_mcp_dispatch(self) -> None:
        import gazelle_mcp

        result = gazelle_mcp._dispatch(
            "gazelle_commit",
            {"summary": "MCP test", "session_date": "2099-06-01", "dry_run": True},
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
        inspect_fact.assert_called_once_with(fact_row, force=False)


class CheckStaleTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self.nest = Path(self._tmpdir) / "nest"
        self.nest.mkdir()
        self.cases = Path(self._tmpdir) / "cases"
        self.cases.mkdir()

    def tearDown(self) -> None:
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_stale_when_source_newer(self) -> None:
        import case_store

        src = self.nest / "coparent.db"
        dest = self.cases / "coparent.db"
        dest.write_bytes(b"old")
        import time
        time.sleep(0.01)
        src.write_bytes(b"new")

        with (
            mock.patch.object(case_store, "CASES_DIR", self.cases),
            mock.patch.object(case_store, "DEFAULT_SOURCE", self.nest),
        ):
            stale = case_store.check_stale(self.nest)
        self.assertIn("coparent.db", stale)

    def test_not_stale_when_dest_current(self) -> None:
        import case_store

        src = self.nest / "coparent.db"
        src.write_bytes(b"data")
        import shutil as _shutil
        dest = self.cases / "coparent.db"
        _shutil.copy2(src, dest)

        with (
            mock.patch.object(case_store, "CASES_DIR", self.cases),
            mock.patch.object(case_store, "DEFAULT_SOURCE", self.nest),
        ):
            stale = case_store.check_stale(self.nest)
        self.assertNotIn("coparent.db", stale)

    def test_milestones_falls_back_to_constants_when_no_json(self) -> None:
        import case_store

        with mock.patch.object(case_store, "response_deadlines", return_value=[]):
            items = case_store.milestones()
        self.assertTrue(len(items) > 0)
        labels = [m["label"] for m in items]
        self.assertTrue(any("Demo cross-matter checkpoint" in l for l in labels))

    def test_milestones_uses_dynamic_data_when_present(self) -> None:
        import case_store

        dynamic = [
            {"deadline": "2099-05-30", "title": "Schedule response", "case": "coparent",
             "source_db": "coparent", "kind": "deadline", "item_type": "deadline",
             "item_id": "deadline:schedule", "deadline_key": "schedule",
             "days_until": -2, "overdue": True, "severity": "URGENT"},
        ]
        with mock.patch.object(case_store, "response_deadlines", return_value=dynamic):
            items = case_store.milestones()
        labels = [m["label"] for m in items]
        self.assertIn("Schedule response", labels)
        self.assertFalse(any("Demo cross-matter checkpoint" in l for l in labels))


if __name__ == "__main__":
    unittest.main()
