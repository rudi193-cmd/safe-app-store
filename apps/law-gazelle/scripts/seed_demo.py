#!/usr/bin/env python3
"""
seed_demo.py — build a synthetic demo Nest for Law Gazelle.

Creates coparent.db, bankruptcy.db, and coparent_db_export.json at the given
destination (default: <app>/.demo/nest). Every row is fictional; demo case
numbers follow the README's synthetic IDs. Deadlines are seeded relative to
today so the urgent queue is alive on any date.

Usage:
    python3 scripts/seed_demo.py [dest_dir]

Stdlib only — safe to run with any python3, no venv required.
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path


def _iso(days_from_today: int) -> str:
    return (date.today() + timedelta(days=days_from_today)).isoformat()


def seed(dest: Path) -> None:
    shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True)

    # ── coparent.db ──────────────────────────────────────────────────────────
    conn = sqlite3.connect(dest / "coparent.db")
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
        CREATE TABLE state_law (id INTEGER PRIMARY KEY, law_id TEXT, statute TEXT, title TEXT, summary TEXT);
        CREATE TABLE context_events (id INTEGER PRIMARY KEY, event_type TEXT, description TEXT, effective_date TEXT);
        CREATE TABLE legal_documents (
            id INTEGER PRIMARY KEY, doc_id TEXT NOT NULL, title TEXT NOT NULL,
            doc_type TEXT, case_number TEXT, effective_date TEXT, signed_date TEXT,
            filed_date TEXT, source_email_thread TEXT, gmail_attachment_id TEXT,
            filename TEXT, mime_type TEXT, content_verified INTEGER DEFAULT 0,
            content_notes TEXT, parties TEXT, attorneys TEXT, mediator TEXT, logged_at TEXT
        );
    """)
    conn.executemany(
        "INSERT INTO atoms (atom_id, type, status, priority, domain, title, body,"
        " legal_ref, related_evidence, related_issue_id, action_required) VALUES"
        " (?,?,?,?,?,?,?,?,?,?,?)",
        [
            ("ATM-001", "gap", "open", "urgent", "schedule",
             "Exchange time conflicts with school pickup",
             "Proposed Thursday exchange at 5pm conflicts with the demo child's "
             "4:45pm school pickup 12 miles away. Counter-proposal needed.",
             "Plan §3.2", '["EVD-2099-001"]', 1, "Draft schedule response"),
            ("ATM-002", "ambiguity", "open", "high", "schedule",
             "Holiday schedule silent on spring break",
             "The parenting plan alternates major holidays but never mentions "
             "spring break. Both parties have assumed opposite defaults.",
             "Plan §4.1", '["EVD-2099-002"]', 1, "Propose explicit spring break clause"),
            ("ATM-003", "gap", "open", "medium", "medical",
             "No shared record of pediatrician visits",
             "Plan requires mutual notice of medical appointments; no mechanism "
             "exists. Two visits this quarter were not communicated.",
             "Plan §6.3", '["EVD-2099-003"]', 2, "Propose shared medical log"),
            ("ATM-004", "dispute", "open", "medium", "expenses",
             "Unreimbursed activity fee",
             "Demo soccer registration ($120) paid by parent A on "
             + _iso(-20) + "; 50% share requested, no response in 14 days.",
             "Plan §7.2", None, None, "Include in all-other response letter"),
        ],
    )
    conn.executemany(
        "INSERT INTO issues (title, description, category, priority, status) VALUES (?,?,?,?,?)",
        [
            ("Schedule friction", "Recurring exchange-time and holiday conflicts.",
             "schedule", "high", "open"),
            ("Information sharing", "Medical and school info not flowing per plan.",
             "communication", "medium", "open"),
        ],
    )
    conn.executemany(
        "INSERT INTO evidence_ledger (evidence_id, category, event_date, description,"
        " verbatim_quote, legal_ref, related_issue_id, content_hash) VALUES (?,?,?,?,?,?,?,?)",
        [
            ("EVD-2099-001", "communication", _iso(-9),
             "Email proposing Thursday 5pm exchange",
             "\"Thursdays at 5 works best for my shift.\"", "Plan §3.2", 1, "demo1"),
            ("EVD-2099-002", "communication", _iso(-30),
             "Text thread showing conflicting spring break assumptions",
             "\"I already booked the cabin that week.\"", "Plan §4.1", 1, "demo2"),
            ("EVD-2099-003", "record", _iso(-15),
             "Pediatrician visit summary not shared until after the fact",
             None, "Plan §6.3", 2, "demo3"),
        ],
    )
    conn.executemany(
        "INSERT INTO plan_citations (section, clause, verbatim_text) VALUES (?,?,?)",
        [
            ("§3.2", "Exchanges",
             "Exchanges shall occur at times that do not interfere with the "
             "child's school attendance."),
            ("§4.1", "Holidays",
             "Major holidays alternate annually between the parties."),
        ],
    )
    conn.execute(
        "INSERT INTO state_law (law_id, statute, title, summary) VALUES (?,?,?,?)",
        ("LAW-001", "Demo Rev. Stat. § 00.000",
         "Best interests of the child (demo)",
         "Synthetic placeholder for a best-interests factors statute."),
    )
    conn.executemany(
        "INSERT INTO context_events (event_type, description, effective_date) VALUES (?,?,?)",
        [
            ("letter_received", "Demo letter from other party raising schedule changes", _iso(-10)),
            ("order_entered", "Demo parenting plan order entered", _iso(-180)),
        ],
    )
    conn.execute(
        "INSERT INTO legal_documents (doc_id, title, doc_type, case_number,"
        " effective_date, signed_date, filed_date, filename, content_verified,"
        " content_notes, logged_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        ("DOC-001", "Parenting Plan Order (demo)", "court_order",
         "D-000-DM-0000-00000", _iso(-180), _iso(-185), _iso(-182),
         "parenting_plan_demo.pdf", 1,
         "Synthetic order. Controls exchanges, holidays, medical notice.",
         _iso(-179) + "T00:00:00"),
    )
    conn.commit()
    conn.close()

    (dest / "coparent_db_export.json").write_text(
        json.dumps({"_meta": {"response_deadlines": {
            "schedule": _iso(6), "all_other": _iso(30)}}}, indent=2),
        encoding="utf-8",
    )

    # ── bankruptcy.db ────────────────────────────────────────────────────────
    conn = sqlite3.connect(dest / "bankruptcy.db")
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
    conn.executemany(
        "INSERT INTO critical_flags (flag_id, severity, title, description,"
        " action_required, deadline, resolved) VALUES (?,?,?,?,?,?,?)",
        [
            ("FLAG-001", "URGENT", "Means test paperwork incomplete",
             "Demo pay stubs for months 4-6 missing from the packet.",
             "Gather remaining demo pay stubs", _iso(12), 0),
            ("FLAG-002", "HIGH", "341 meeting prep",
             "Synthetic reminder: review demo questions before creditor meeting.",
             "Review 341 prep sheet", _iso(25), 0),
        ],
    )
    conn.execute(
        "INSERT INTO coparent_intersections (issue, bankruptcy_impact,"
        " coparent_impact, action) VALUES (?,?,?,?)",
        ("Housing (demo)", "Residence listed as exempt asset",
         "Parenting plan assumes child's school district",
         "Coordinate any move date across both matters"),
    )
    conn.execute(
        "INSERT INTO case_registry (case_id, chapter, status, notes) VALUES (?,?,?,?)",
        ("BK-0000-DEMO", 7, "open", "Synthetic demo matter."),
    )
    conn.executemany(
        "INSERT INTO document_checklist (doc_type, status, priority, description) VALUES (?,?,?,?)",
        [
            ("pay_stubs", "partial", "high", "6 months required; 3 collected (demo)"),
            ("tax_returns", "complete", "medium", "2 years collected (demo)"),
        ],
    )
    conn.executemany(
        "INSERT INTO creditors (creditor_id, name, debt_type, amount_owed) VALUES (?,?,?,?)",
        [
            ("CRD-001", "Demo Medical Group", "medical", 2400.00),
            ("CRD-002", "Example Card Services", "credit_card", 5150.00),
        ],
    )
    conn.commit()
    conn.close()

    # ── workers_comp.db ──────────────────────────────────────────────────────
    conn = sqlite3.connect(dest / "workers_comp.db")
    conn.executescript("""
        CREATE TABLE context_events (id INTEGER PRIMARY KEY, event_type TEXT, description TEXT, effective_date TEXT);
    """)
    conn.execute(
        "INSERT INTO context_events (event_type, description, effective_date) VALUES (?,?,?)",
        ("claim_filed", "Demo claim filed (WCA 00-00000)", _iso(-90)),
    )
    conn.commit()
    conn.close()

    print(f"Synthetic demo Nest seeded at {dest}")
    print("  coparent.db (4 atoms, 3 evidence, 1 order), bankruptcy.db (2 flags),")
    print(f"  workers_comp.db, deadlines: schedule {_iso(6)}, all_other {_iso(30)}")


if __name__ == "__main__":
    default = Path(__file__).resolve().parent.parent / ".demo" / "nest"
    seed(Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else default)
