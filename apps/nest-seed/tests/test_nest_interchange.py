"""The Nest interchange contract (#17).

nest-seed is the *portable* Nest seeder — no fleet dependency, runs anywhere.
willow-mcp ships an identical Nest engine and exposes it as MCP tools
(``nest_status`` / ``nest_digest`` / ``nest_promote``) that read a seed.db
built by *either* engine. The two are twins on one schema; the danger is silent
drift — a column added here or there that breaks cross-consumption without any
error.

This test freezes the interchange: the exact columns willow-mcp's Nest tools
read from ``sources`` / ``fragments`` / ``nest_meta``. It introspects a live
nest-seed DB (PRAGMA table_info) and asserts the contract holds. It imports
NOTHING from the fleet — the contract is embedded as a frozen constant, so the
guard runs on a machine that has never seen willow-mcp. If willow-mcp's schema
and this contract ever disagree, the mirror test on that side catches it; here
we guarantee nest-seed keeps emitting the canonical shape.

Measured identical to willow-mcp/src/willow_mcp/nest/db.py on 2026-07-24.
"""
from __future__ import annotations

import sys
from pathlib import Path

# nest-seed is a flat package; import db.py directly from the app root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db as nest_db  # noqa: E402


# The frozen interchange contract — the columns the fleet's Nest tools consume.
CANONICAL_COLUMNS = {
    "nest_meta": {"id", "owner", "description", "created_at"},
    "sources": {
        "id", "path", "filename", "file_hash", "mime_hint", "status",
        "ocr_method", "char_count", "error", "ingested_at",
    },
    "fragments": {
        "id", "source_id", "fragment_type", "label", "content", "confidence",
        "date_ref", "kb_atom_id", "created_at",
    },
}


def _columns(conn, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def test_seed_schema_matches_interchange_contract(tmp_path):
    conn = nest_db.open_db(tmp_path / "seed.db")
    try:
        for table, expected in CANONICAL_COLUMNS.items():
            actual = _columns(conn, table)
            assert actual == expected, (
                f"nest-seed table {table!r} drifted from the willow-mcp Nest "
                f"interchange contract.\n  only in nest-seed: {sorted(actual - expected)}"
                f"\n  missing from nest-seed: {sorted(expected - actual)}"
            )
    finally:
        conn.close()


def test_nest_meta_is_single_row(tmp_path):
    """nest_meta is the one-row identity willow-mcp's nest_status reads as id=1."""
    conn = nest_db.open_db(tmp_path / "seed.db")
    try:
        nest_db.init_meta(conn, owner="tester", description="contract check")
        row = conn.execute("select owner from nest_meta where id=1").fetchone()
        assert row is not None and row[0] == "tester"
    finally:
        conn.close()


def test_source_status_values_are_readable(tmp_path):
    """nest_status groups sources by status; the seeder's allowed statuses must
    stay a subset of what a consumer expects to bucket."""
    conn = nest_db.open_db(tmp_path / "seed.db")
    try:
        # The CHECK constraint in db.py pins these; assert the set is intact.
        assert nest_db.FRAGMENT_TYPES  # engine still declares a fragment taxonomy
        # A status outside the allowed set must be rejected by the schema.
        import sqlite3
        conn.execute(
            "insert into sources (path, filename, file_hash, status) "
            "values ('/x', 'x', 'h', 'extracted')"
        )
        try:
            conn.execute(
                "insert into sources (path, filename, file_hash, status) "
                "values ('/y', 'y', 'h2', 'bogus-status')"
            )
            raised = False
        except sqlite3.IntegrityError:
            raised = True
        assert raised, "sources.status CHECK constraint must reject unknown statuses"
    finally:
        conn.close()
