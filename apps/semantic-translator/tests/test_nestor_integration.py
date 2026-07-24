"""Integration: semantic-translator consuming the standalone `nestor` package.

Covers the wiring seam end to end:
  * the host adapter satisfies nestor's runtime-checkable Storage Protocol,
  * translate_text writes a document + segments into the app's own DB,
  * a sealed pair is served as a tier-1 memory hit,
  * memory_stats returns the expected shape.

Everything runs against a temp DB and a temp ledger so nothing touches the repo.
The offline engine is used so no network / API key is required.
"""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest

import nestor
from nestor import memory, storage
from nestor.storage import Storage

from semantic_translator import db
from semantic_translator.nestor_store import SemanticTranslatorStore
from semantic_translator.nestor_wiring import configure_nestor


@pytest.fixture()
def wired(tmp_path, monkeypatch):
    """Configure nestor over a temp DB + temp ledger."""
    # Redirect the app DB and the nestor ledger into the tmp dir.
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "translator.db")
    monkeypatch.setenv("NESTOR_LEDGER", str(tmp_path / "ledger.jsonl"))

    # configure_nestor() is idempotent via a module-level flag; reset it so this
    # test actually (re)installs the store against a clean import state.
    import semantic_translator.nestor_wiring as wiring
    monkeypatch.setattr(wiring, "_configured", False)
    wiring.configure_nestor()
    yield tmp_path


def test_store_satisfies_protocol():
    # runtime_checkable Protocol — structural conformance of the adapter.
    assert isinstance(SemanticTranslatorStore(), Storage)


def test_configure_is_idempotent(wired):
    # Calling again is a harmless no-op and leaves the global store installed.
    configure_nestor()
    assert isinstance(storage.get_store(), SemanticTranslatorStore)


def test_translate_text_creates_document_and_segments(wired):
    text = "Hello there.\n\nThis is a second paragraph."
    doc, passages = nestor.translate_text(
        text, target_lang="es", source_lang="en",
        engine_name="offline", title="greeting",
    )

    assert doc["id"]
    stored = db.get_document(doc["id"])
    assert stored is not None
    assert stored["source_lang"] == "en"
    assert stored["target_lang"] == "es"

    # Every non-tier-1 passage is queued as a real segment row.
    assert passages
    segs = db.get_segments(doc["id"])
    assert len(segs) == len(passages)
    for seg in segs:
        assert seg["document_id"] == doc["id"]


def test_sealed_pair_served_as_tier_one(wired):
    src = "Good morning, everyone."
    memory.add_pair(src, "Buenos días a todos.", "en", "es",
                    status="sealed", verifier="native")

    hit = memory.best_sealed(src, "en", "es")
    assert hit is not None
    assert hit["pair"]["target_text"] == "Buenos días a todos."
    assert hit["similarity"] >= memory.SEAL_THRESHOLD

    # And the cascade serves it directly from memory (tier 1, no engine).
    _doc, passages = nestor.translate_text(
        src, target_lang="es", source_lang="en", engine_name="offline",
    )
    assert any(p.tier == 1 and p.target == "Buenos días a todos." for p in passages)


def test_memory_stats_shape(wired):
    memory.add_pair("one", "uno", "en", "es", status="sealed", verifier="x")
    memory.add_pair("two", "dos", "en", "es")  # draft

    s = memory.stats()
    assert set(s) == {"total", "sealed", "draft", "lang_pairs"}
    assert s["total"] == 2
    assert s["sealed"] == 1
    assert s["draft"] == 1
    assert ("en", "es", 2) in s["lang_pairs"]
