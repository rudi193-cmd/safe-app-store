"""Tests for Law Gazelle document drafting and Nest output."""

from __future__ import annotations

import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import case_store
import document_store
import gazelle_state


class DocumentStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self.app_data = Path(self._tmpdir) / "app"
        self.cases_dir = self.app_data / "cases"
        self.cases_dir.mkdir(parents=True)
        self.nest = Path(self._tmpdir) / "nest"
        self.nest.mkdir()

        self._patches = [
            mock.patch.object(case_store, "APP_DATA", self.app_data),
            mock.patch.object(case_store, "CASES_DIR", self.cases_dir),
            mock.patch.object(case_store, "DEFAULT_SOURCE", self.nest),
            mock.patch.object(gazelle_state, "APP_DATA", self.app_data),
            mock.patch.object(
                gazelle_state, "STATE_DB", self.app_data / "gazelle_state.db"
            ),
        ]
        for p in self._patches:
            p.start()
        # document_store binds NEST at import; patch module attribute too
        self._patch_nest = mock.patch.object(document_store, "NEST", self.nest)
        self._patch_nest.start()

        self._seed_minimal_dbs()

    def tearDown(self) -> None:
        for p in self._patches:
            p.stop()
        self._patch_nest.stop()
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _seed_minimal_dbs(self) -> None:
        cp = self.cases_dir / "coparent.db"
        conn = sqlite3.connect(cp)
        conn.executescript("""
            CREATE TABLE atoms (
                id INTEGER PRIMARY KEY, atom_id TEXT, type TEXT, status TEXT,
                priority TEXT, domain TEXT, title TEXT, body TEXT, legal_ref TEXT,
                related_evidence TEXT, related_issue_id INTEGER, action_required TEXT, flag TEXT
            );
            CREATE TABLE issues (
                id INTEGER PRIMARY KEY, title TEXT, description TEXT,
                category TEXT, priority TEXT, status TEXT
            );
            CREATE TABLE evidence_ledger (
                id INTEGER PRIMARY KEY, evidence_id TEXT UNIQUE, category TEXT,
                event_date TEXT, description TEXT, verbatim_quote TEXT,
                legal_ref TEXT, related_issue_id INTEGER, content_hash TEXT
            );
            CREATE TABLE plan_citations (id INTEGER PRIMARY KEY, section TEXT, clause TEXT, verbatim_text TEXT);
            CREATE TABLE state_law (
                id INTEGER PRIMARY KEY, law_id TEXT, statute TEXT, title TEXT, summary TEXT
            );
            CREATE TABLE context_events (
                id INTEGER PRIMARY KEY, event_type TEXT, description TEXT, effective_date TEXT
            );
        """)
        conn.execute(
            "INSERT INTO atoms VALUES (1,'ATM-001','gap','open','urgent','schedule','Thu exchange','Body',NULL,NULL,NULL,'Act',NULL)"
        )
        conn.execute(
            "INSERT INTO context_events VALUES (1,'order','Parenting plan entered','2024-03-15')"
        )
        conn.execute(
            "INSERT INTO context_events VALUES (2,'violation','Missed Thursday exchange','2099-05-10')"
        )
        conn.commit()
        conn.close()

        meta = self.cases_dir / "coparent_db_export.json"
        meta.write_text(
            """{
              "_meta": {
                "case": "D-000-DM-0000-00000",
                "parties": {"parent_a": "Example Parent A", "parent_b": "Example Parent B"},
                "letter_sent": "2099-05-23",
                "response_deadlines": {"schedule": "2099-01-01", "all_other": "2099-06-01"}
              }
            }""",
            encoding="utf-8",
        )

    def test_draft_context_unknown_type(self) -> None:
        ctx = document_store.draft_context("invalid")
        self.assertIn("error", ctx)

    def test_draft_context_schedule_response(self) -> None:
        ctx = document_store.draft_context("schedule_response")
        self.assertEqual(ctx["doc_type"], "schedule_response")
        self.assertIn("ATM-001", ctx["atom_ids"])
        self.assertIn("structure_template", ctx)
        self.assertIn("schedule_packet", ctx)
        self.assertIn("chronology", ctx)
        self.assertGreater(ctx["chronology"]["event_count"], 0)
        md = document_store.format_draft_context_markdown(ctx)
        self.assertIn("Schedule Response", md)
        self.assertIn("Case Chronology", md)
        self.assertIn("gazelle_save", md)

    def test_structure_template_schedule(self) -> None:
        tpl = document_store.structure_template("schedule_response")
        self.assertIn("case response deadline", tpl)
        self.assertIn("Example Parent A", tpl)

    def test_save_document_to_nest(self) -> None:
        result = document_store.save_document(
            "CaseDraft_test_draft",
            "# Test Letter\n\nBody text.",
        )
        self.assertTrue(result["ok"])
        path = Path(result["path"])
        self.assertTrue(path.exists())
        self.assertEqual(path.parent, self.nest / "drafts")
        self.assertIn("Test Letter", path.read_text(encoding="utf-8"))

    def test_save_document_adds_disclosure(self) -> None:
        result = document_store.save_document("plain.txt", "Dear Example Parent B,\n\nThanks.")
        path = Path(result["path"])
        text = path.read_text(encoding="utf-8")
        self.assertIn("AI assistance", text)

    def test_save_document_rejects_empty(self) -> None:
        result = document_store.save_document("empty.md", "   ")
        self.assertIn("error", result)

    def test_list_drafts(self) -> None:
        document_store.save_document("listed.md", "# Listed draft")
        drafts = document_store.list_drafts()
        names = [d["name"] for d in drafts]
        self.assertIn("listed.md", names)

    def test_sync_copies_nest_drafts(self) -> None:
        nest_draft = self.nest / "drafts" / "from_nest.md"
        nest_draft.parent.mkdir(parents=True)
        nest_draft.write_text("# From Nest", encoding="utf-8")
        result = case_store.sync_cases(self.nest)
        self.assertIn("from_nest.md", result["copied"])
        self.assertTrue((self.cases_dir / "drafts" / "from_nest.md").exists())

    def test_chronology_builder_events_and_gaps(self) -> None:
        chrono = document_store.chronology_builder("coparent")
        self.assertEqual(chrono["case"], "coparent")
        self.assertGreaterEqual(chrono["event_count"], 4)
        types = {e["type"] for e in chrono["events"]}
        self.assertIn("order", types)
        self.assertIn("violation", types)
        self.assertIn("letter_sent", types)
        self.assertIn("deadline", types)
        violation = next(e for e in chrono["events"] if e["type"] == "violation")
        self.assertEqual(violation["significance"], "🔴")

    def test_format_chronology_markdown(self) -> None:
        chrono = document_store.chronology_builder("coparent")
        md = document_store.format_chronology_markdown(chrono)
        self.assertIn("# Case Chronology", md)
        self.assertIn("| Date | Sig |", md)
        self.assertIn("2099-05-23", md)
        self.assertIn("[VERIFY", md)

    def test_structure_template_has_fact_flags(self) -> None:
        tpl = document_store.structure_template("schedule_response")
        self.assertIn("[FACT NEEDED", tpl)
        self.assertIn("[VERIFY", tpl)


if __name__ == "__main__":
    unittest.main()
