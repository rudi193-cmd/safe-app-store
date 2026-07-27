"""Tests for the shared Nest pipeline core (box audit A4).

These exercise the canonical library directly — the import surface every
consumer (nest-seed, willow-mcp) relies on, plus a few pure, offline-safe
functions. The third-party extractors and the Ollama HTTP calls are lazy, so
nothing here needs tesseract, pdfplumber, or a running model.
"""
import sqlite3

from nest_pipeline import (
    classify,
    db,
    embed,
    ingest,
    llm,
    ocr,
    secrets,
    selflearn,
    taxonomy,
)


# ── import surface ────────────────────────────────────────────────────────────

def test_public_modules_import_stdlib_only():
    # Importing the package must not require any third-party package.
    for mod in (classify, db, embed, ingest, llm, ocr, secrets, selflearn, taxonomy):
        assert mod is not None

    # The intra-package relative imports resolved (no leftover script-dir mode).
    assert classify._embed is embed
    assert classify._llm is llm
    assert classify._tax is taxonomy
    assert ingest._db is db
    assert taxonomy._embed is embed


# ── db: the portable Nest schema ───────────────────────────────────────────────

def test_open_db_creates_nest_schema(tmp_path):
    conn = db.open_db(tmp_path / "seed.db")
    try:
        tables = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert {"sources", "fragments", "nest_meta"} <= tables
    finally:
        conn.close()


def test_stats_on_empty_db(tmp_path):
    conn = db.open_db(tmp_path / "seed.db")
    try:
        st = db.stats(conn)
        # stats() buckets counts by status / fragment_type; empty DB -> empty buckets.
        assert st["sources"] == {}
        assert st["fragments"] == {}
    finally:
        conn.close()


# ── secrets: the credential guard ──────────────────────────────────────────────

def test_redact_value_masks_middle():
    red = secrets.redact_value("abcdef123456")
    assert "123456" not in red
    assert red != "abcdef123456"


def test_placeholder_is_not_a_secret():
    # An obvious placeholder assignment must not be flagged as a live credential.
    assert secrets.find_secrets("api_key = 'your-key-here'") == []


# ── classify: pure date hardening (offline) ────────────────────────────────────

def test_plausible_date_rejects_semver_accepts_real_date():
    assert classify._plausible_date("0.4.27") is False
    assert classify._plausible_date("2021-06-14") is True
