"""Tests for Law Gazelle case store and sidecar."""

from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

import case_store
import gazelle_state


class CaseStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self.app_data = Path(self._tmpdir) / "app"
        self.cases_dir = self.app_data / "cases"
        self.cases_dir.mkdir(parents=True)
        self.nest = Path(self._tmpdir) / "nest"
        self.nest.mkdir()

        self._patch_app = mock.patch.object(case_store, "APP_DATA", self.app_data)
        self._patch_cases = mock.patch.object(case_store, "CASES_DIR", self.cases_dir)
        self._patch_state_app = mock.patch.object(gazelle_state, "APP_DATA", self.app_data)
        self._patch_state_db = mock.patch.object(
            gazelle_state, "STATE_DB", self.app_data / "gazelle_state.db"
        )
        self._patch_app.start()
        self._patch_cases.start()
        self._patch_state_app.start()
        self._patch_state_db.start()

        self._seed_minimal_dbs()

    def tearDown(self) -> None:
        self._patch_app.stop()
        self._patch_cases.stop()
        self._patch_state_app.stop()
        self._patch_state_db.stop()
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
            "INSERT INTO atoms VALUES (1,'ATM-001','gap','open','urgent','schedule','T','B',NULL,NULL,NULL,'Act',NULL)"
        )
        conn.execute(
            "INSERT INTO evidence_ledger VALUES (1,'EVD-2099-001','comm','2099-01-01','desc','quote',NULL,NULL,'abc')"
        )
        conn.commit()
        conn.close()

        meta = self.cases_dir / "coparent_db_export.json"
        meta.write_text(
            '{"_meta":{"response_deadlines":{"schedule":"2099-01-01","all_other":"2099-06-01"}}}',
            encoding="utf-8",
        )

        bk = self.cases_dir / "bankruptcy.db"
        conn = sqlite3.connect(bk)
        conn.executescript("""
            CREATE TABLE critical_flags (
                id INTEGER PRIMARY KEY, flag_id TEXT, severity TEXT, title TEXT,
                description TEXT, action_required TEXT, deadline TEXT, resolved INTEGER
            );
            CREATE TABLE coparent_intersections (
                id INTEGER PRIMARY KEY, issue TEXT, bankruptcy_impact TEXT, coparent_impact TEXT, action TEXT
            );
            CREATE TABLE case_registry (id INTEGER PRIMARY KEY, case_id TEXT, chapter INTEGER, status TEXT, notes TEXT);
            CREATE TABLE document_checklist (id INTEGER PRIMARY KEY, doc_type TEXT, status TEXT, priority TEXT, description TEXT);
            CREATE TABLE creditors (id INTEGER PRIMARY KEY, creditor_id TEXT, name TEXT, debt_type TEXT, amount_owed REAL);
        """)
        conn.execute(
            "INSERT INTO critical_flags VALUES (1,'FLAG-001','URGENT','T','D','A','2099-12-31',0)"
        )
        conn.execute(
            "INSERT INTO coparent_intersections VALUES (1,'Housing','bk','cp','act')"
        )
        conn.commit()
        conn.close()

        nest_cp = self.nest / "coparent.db"
        nest_bk = self.nest / "bankruptcy.db"
        shutil.copy(cp, nest_cp)
        shutil.copy(bk, nest_bk)
        shutil.copy(meta, self.nest / "coparent_db_export.json")

    def test_sync_copies_from_nest(self) -> None:
        result = case_store.sync_cases(self.nest)
        self.assertIn("coparent.db", result["skipped"] or result["copied"])

    def test_urgent_queue_orders_overdue_first(self) -> None:
        past = (date.today() - timedelta(days=1)).isoformat()
        conn = sqlite3.connect(self.cases_dir / "coparent.db")
        conn.execute(
            "INSERT INTO atoms VALUES (2,'ATM-002','gap','open','urgent','f','Past','B',NULL,NULL,NULL,'Act',NULL)"
        )
        conn.commit()
        conn.close()
        meta = self.cases_dir / "coparent_db_export.json"
        meta.write_text(
            f'{{"_meta":{{"response_deadlines":{{"schedule":"{past}"}}}}}}',
            encoding="utf-8",
        )
        items = case_store.urgent_queue()
        self.assertTrue(items[0].get("overdue"))

    def test_sidecar_marks_resolved(self) -> None:
        gazelle_state.mark_resolved("bankruptcy", "flag", "FLAG-001")
        items = case_store.urgent_queue(show_resolved=False)
        ids = [i.get("item_id") for i in items]
        self.assertNotIn("FLAG-001", ids)
        items_all = case_store.urgent_queue(show_resolved=True)
        self.assertIn("FLAG-001", [i.get("item_id") for i in items_all])

    def test_get_atom_detail(self) -> None:
        detail = case_store.get_atom_detail("ATM-001")
        self.assertIsNotNone(detail)
        self.assertEqual(detail["atom"]["title"], "T")

    def test_get_flag_detail(self) -> None:
        detail = case_store.get_flag_detail("FLAG-001")
        self.assertIsNotNone(detail)
        self.assertEqual(detail["flag"]["flag_id"], "FLAG-001")

    def test_cross_case_overview(self) -> None:
        cc = case_store.cross_case_overview()
        self.assertEqual(len(cc["intersections"]), 1)
        self.assertEqual(len(cc["milestones"]), 3)

    def test_milestones_days_until(self) -> None:
        ms = case_store.milestones()
        self.assertTrue(all("days_until" in m for m in ms))

    def test_schedule_response_packet(self) -> None:
        packet = case_store.schedule_response_packet()
        self.assertEqual(packet["kind"], "schedule_response")
        self.assertEqual(packet["deadline"]["key"], "schedule")
        self.assertGreaterEqual(packet["atom_count"], 1)
        self.assertTrue(any(p["atom_id"] == "ATM-001" for p in packet["proposals"]))
        text = case_store.format_schedule_response_text(packet)
        self.assertIn("ATM-001", text)
        self.assertIn("Schedule Response Briefing", text)


if __name__ == "__main__":
    unittest.main()
