"""Scaffold workers_comp.db in Nest from known WCA 00-00000 context."""

from __future__ import annotations

import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

NEST = Path(os.environ.get("NEST_SOURCE", Path.home() / "Desktop" / "Nest"))
OUT = NEST / "workers_comp.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS case_registry (
    id INTEGER PRIMARY KEY,
    case_number TEXT UNIQUE,
    case_type TEXT,
    status TEXT,
    jurisdiction TEXT,
    employer TEXT,
    injury_date TEXT,
    notes TEXT,
    logged_at TEXT
);
CREATE TABLE IF NOT EXISTS atoms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    atom_id TEXT UNIQUE NOT NULL,
    type TEXT NOT NULL,
    status TEXT DEFAULT 'open',
    priority TEXT DEFAULT 'normal',
    domain TEXT,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    legal_ref TEXT,
    action_required TEXT,
    logged_at TEXT
);
CREATE TABLE IF NOT EXISTS evidence_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    evidence_id TEXT UNIQUE NOT NULL,
    category TEXT NOT NULL,
    event_date TEXT,
    description TEXT NOT NULL,
    source TEXT,
    logged_at TEXT
);
CREATE TABLE IF NOT EXISTS deadlines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    deadline_date TEXT,
    status TEXT DEFAULT 'pending',
    notes TEXT
);
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id TEXT UNIQUE,
    title TEXT,
    doc_type TEXT,
    notes TEXT
);
"""

_SEED_ATOMS = [
    (
        "WCA-001", "fact", "open", "urgent", "medical",
        "Work-Related Back Injury",
        "Work-related back injury sustained during employment at Example Employer Inc.",
        "State Workers' Compensation Act",
        "Maintain medical records chain for surgery consult and WCA hearing.",
    ),
    (
        "WCA-002", "action", "open", "high", "claim",
        "WCA No. 00-00000 — Active Claim",
        "Doe v. Example Employer Inc. State Workers' Compensation Administration.",
        "WCA 00-00000",
        "Track mediation correspondence and employer responses.",
    ),
    (
        "WCA-003", "deadline", "open", "high", "medical",
        "Surgery Consult — Late May 2026",
        "Surgery consultation scheduled. Document outcome for support modification (July 1).",
        None,
        "Obtain consult notes; link to coparent ATM-020 modification window.",
    ),
    (
        "WCA-004", "gap", "open", "normal", "financial",
        "Income Gap — May 2025 through July 1 2026",
        "~12 months reduced income. Basis for child support arrears and bankruptcy. Involuntary underemployment.",
        "State child support statute",
        "Use WCA records for Motion to Modify filed July 1.",
    ),
]


def main() -> int:
    if OUT.exists():
        print(f"Already exists: {OUT}")
        print("Delete manually to re-scaffold.")
        return 0

    NEST.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn = sqlite3.connect(OUT)
    conn.executescript(_SCHEMA)
    conn.execute(
        """
        INSERT INTO case_registry
        (id, case_number, case_type, status, jurisdiction, employer, injury_date, notes, logged_at)
        VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "WCA 00-00000",
            "workers_comp",
            "open",
            "State WCA",
            "Example Employer Inc.",
            "2025-05-01",
            "Back injury; mediation active; surgery consult May 2026.",
            now,
        ),
    )
    for row in _SEED_ATOMS:
        conn.execute(
            """
            INSERT INTO atoms
            (atom_id, type, status, priority, domain, title, body, legal_ref, action_required, logged_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (*row, now),
        )
    conn.execute(
        """
        INSERT INTO evidence_ledger
        (evidence_id, category, event_date, description, source, logged_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "WCA-EVD-001",
            "medical",
            "2025-05-01",
            "Work-related back injury; workers comp claim filed; ~12 months reduced income.",
            "coparent EVD-2026-009 cross-ref",
            now,
        ),
    )
    conn.execute(
        """
        INSERT INTO deadlines (title, deadline_date, status, notes)
        VALUES (?, ?, ?, ?)
        """,
        (
            "Surgery consultation",
            "2026-05-31",
            "pending",
            "Late May 2026 per session records.",
        ),
    )
    conn.execute(
        """
        INSERT INTO documents (doc_id, title, doc_type, notes)
        VALUES (?, ?, ?, ?)
        """,
        (
            "DOC-WCA-001",
            "Deep Dive Workers' Comp Legal Research.pdf",
            "research",
            "Referenced in client_profile; file not on local disk yet.",
        ),
    )
    conn.commit()
    conn.close()
    print(f"Scaffolded {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
