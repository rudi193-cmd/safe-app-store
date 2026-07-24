"""Host adapter: the semantic-translator DB as a Nestor ``Storage``.

Nestor (the standalone package) owns translation logic but no persistence —
every database touch goes through its :class:`nestor.storage.Storage` Protocol.
This module implements that Protocol over the app's own ``semantic_translator.db``
module, so Nestor writes into the same ``data/translator.db`` the rest of the app
already uses.

Documents and segments map straight onto ``db.create_document`` / ``db.create_segment``
and friends. The translation-memory methods (the ``tm_pairs`` table) are ported
verbatim from the old embedded ``semantic_translator/nestor/memory.py`` so the
data model and SQL are byte-for-byte unchanged — same table, same columns, same
index, same queries.

Install it once at startup via :mod:`semantic_translator.nestor_wiring`.
"""
from __future__ import annotations

from typing import Optional

from . import db

# Ported verbatim from the old embedded semantic_translator/nestor/memory.py.
# The tm_pairs data model is unchanged — do not alter columns or the index
# without a migration.
_TM_SCHEMA = """
CREATE TABLE IF NOT EXISTS tm_pairs (
    id          TEXT PRIMARY KEY,
    source_text TEXT NOT NULL,
    source_norm TEXT NOT NULL,
    source_lang TEXT NOT NULL,
    target_text TEXT NOT NULL,
    target_lang TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'draft',
    verifier    TEXT NOT NULL DEFAULT '',
    weight      REAL NOT NULL DEFAULT 1.0,
    origin      TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tm_langs ON tm_pairs(source_lang, target_lang, status);
"""


class SemanticTranslatorStore:
    """Implements :class:`nestor.storage.Storage` over ``semantic_translator.db``."""

    # --- lifecycle -------------------------------------------------------

    def init_db(self) -> None:
        db.init_db()

    # --- documents -------------------------------------------------------

    def create_document(self, title: str, source_lang: str,
                        target_lang: str) -> dict:
        return db.create_document(title=title, source_lang=source_lang,
                                  target_lang=target_lang)

    def get_document(self, document_id: str) -> Optional[dict]:
        return db.get_document(document_id)

    def update_document_status(self, document_id: str, status: str) -> None:
        db.update_document_status(document_id, status)

    # --- segments --------------------------------------------------------

    def create_segment(self, document_id: str, position: int,
                       source_text: str, candidate: str,
                       jeles_score: float) -> dict:
        return db.create_segment(document_id=document_id, position=position,
                                 source_text=source_text, candidate=candidate,
                                 jeles_score=jeles_score)

    def get_segment(self, segment_id: str) -> Optional[dict]:
        return db.get_segment(segment_id)

    # --- translation memory (tier 1) ------------------------------------
    #
    # Ported verbatim from the old embedded nestor/memory.py raw SQL, keyed
    # off db.get_db(). The tm_pairs table/columns are unchanged.

    def memory_init(self) -> None:
        db.init_db()
        with db.get_db() as conn:
            conn.executescript(_TM_SCHEMA)

    def memory_find(self, source_norm: str, source_lang: str,
                   target_lang: str) -> Optional[dict]:
        with db.get_db() as conn:
            row = conn.execute(
                "SELECT * FROM tm_pairs WHERE source_norm=? AND source_lang=? AND target_lang=?",
                (source_norm, source_lang, target_lang),
            ).fetchone()
            return dict(row) if row else None

    def memory_insert(self, pair: dict) -> None:
        with db.get_db() as conn:
            conn.execute(
                "INSERT INTO tm_pairs VALUES (:id,:source_text,:source_norm,:source_lang,"
                ":target_text,:target_lang,:status,:verifier,:weight,:origin,:created_at)",
                pair,
            )

    def memory_seal(self, pair_id: str, target_text: str, verifier: str,
                   weight: float) -> None:
        with db.get_db() as conn:
            conn.execute(
                "UPDATE tm_pairs SET target_text=?, status='sealed', verifier=?, weight=? WHERE id=?",
                (target_text, verifier, weight, pair_id),
            )

    def memory_candidates(self, source_lang: str,
                         target_lang: str) -> list[dict]:
        with db.get_db() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM tm_pairs WHERE source_lang=? AND target_lang=?",
                (source_lang, target_lang),
            )]

    def memory_stats(self) -> dict:
        with db.get_db() as conn:
            total = conn.execute("SELECT COUNT(*) FROM tm_pairs").fetchone()[0]
            sealed = conn.execute(
                "SELECT COUNT(*) FROM tm_pairs WHERE status='sealed'"
            ).fetchone()[0]
            langs = [tuple(r) for r in conn.execute(
                "SELECT source_lang, target_lang, COUNT(*) FROM tm_pairs "
                "GROUP BY source_lang, target_lang ORDER BY 3 DESC")]
        return {"total": total, "sealed": sealed, "draft": total - sealed,
                "lang_pairs": langs}
