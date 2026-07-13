"""Nestor's ledger — the translation memory. Tier 1 of the cascade.

Verified pairs live in sqlite alongside the existing schema. A pair is
"sealed" (human-verified or curated-corpus) or "draft" (machine, awaiting
seal). Tier-1 serving uses sealed pairs only; drafts may be offered as
context to the engine but never served as verified.
"""
from __future__ import annotations

import difflib
import re
import uuid
from datetime import datetime, timezone

from .. import db

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

EXACT = 1.0
SEAL_THRESHOLD = 0.92   # fuzzy similarity at/above which a sealed pair serves as tier 1
CONTEXT_THRESHOLD = 0.55  # pairs above this feed the engine as context


def init_tm() -> None:
    db.init_db()
    with db.get_db() as conn:
        conn.executescript(_TM_SCHEMA)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", text.lower())).strip()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def add_pair(source_text: str, target_text: str, source_lang: str, target_lang: str,
             status: str = "draft", verifier: str = "", weight: float = 1.0,
             origin: str = "") -> dict:
    """Insert or upgrade a pair. A sealed insert replaces a draft for the same source."""
    init_tm()
    norm = _norm(source_text)
    with db.get_db() as conn:
        row = conn.execute(
            "SELECT * FROM tm_pairs WHERE source_norm=? AND source_lang=? AND target_lang=?",
            (norm, source_lang, target_lang),
        ).fetchone()
        if row:
            if status == "sealed" and (row["status"] != "sealed" or row["target_text"] != target_text):
                conn.execute(
                    "UPDATE tm_pairs SET target_text=?, status='sealed', verifier=?, weight=? WHERE id=?",
                    (target_text, verifier, weight, row["id"]),
                )
            return dict(conn.execute("SELECT * FROM tm_pairs WHERE id=?", (row["id"],)).fetchone())
        pair = dict(id=str(uuid.uuid4()), source_text=source_text, source_norm=norm,
                    source_lang=source_lang, target_text=target_text, target_lang=target_lang,
                    status=status, verifier=verifier, weight=weight, origin=origin,
                    created_at=_now())
        conn.execute(
            "INSERT INTO tm_pairs VALUES (:id,:source_text,:source_norm,:source_lang,"
            ":target_text,:target_lang,:status,:verifier,:weight,:origin,:created_at)", pair)
        return pair


def lookup(source_text: str, source_lang: str, target_lang: str,
           limit: int = 5) -> list[dict]:
    """Ranked matches: [{pair, similarity}], best first. Sealed and draft both returned."""
    init_tm()
    norm = _norm(source_text)
    with db.get_db() as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM tm_pairs WHERE source_lang=? AND target_lang=?",
            (source_lang, target_lang),
        )]
    scored = []
    for row in rows:
        if row["source_norm"] == norm:
            sim = EXACT
        else:
            sim = difflib.SequenceMatcher(None, norm, row["source_norm"]).ratio()
        if sim >= CONTEXT_THRESHOLD:
            scored.append({"pair": row, "similarity": round(sim, 3)})
    scored.sort(key=lambda m: (-m["similarity"], m["pair"]["status"] != "sealed"))
    return scored[:limit]


def best_sealed(source_text: str, source_lang: str, target_lang: str) -> dict | None:
    """Tier-1 check: the best sealed match at/above SEAL_THRESHOLD, else None."""
    for m in lookup(source_text, source_lang, target_lang):
        if m["pair"]["status"] == "sealed" and m["similarity"] >= SEAL_THRESHOLD:
            return m
    return None


def seed_from_corpus(corpus_path: str = "data/corpus.jsonl") -> int:
    """Seed sealed pairs from bilingual lessons in the corpus (curated content)."""
    from ..learn import _load_bilingual_pairs
    import pathlib
    if not pathlib.Path(corpus_path).exists():
        return 0
    count = 0
    for item in _load_bilingual_pairs():
        if item["front"] and item["back"]:
            add_pair(item["front"], item["back"], item["lang_front"], item["lang_back"],
                     status="sealed", verifier="corpus", origin=item["lesson"])
            add_pair(item["back"], item["front"], item["lang_back"], item["lang_front"],
                     status="sealed", verifier="corpus", origin=item["lesson"])
            count += 2
    return count


def stats() -> dict:
    init_tm()
    with db.get_db() as conn:
        total = conn.execute("SELECT COUNT(*) FROM tm_pairs").fetchone()[0]
        sealed = conn.execute("SELECT COUNT(*) FROM tm_pairs WHERE status='sealed'").fetchone()[0]
        langs = [tuple(r) for r in conn.execute(
            "SELECT source_lang, target_lang, COUNT(*) FROM tm_pairs "
            "GROUP BY source_lang, target_lang ORDER BY 3 DESC")]
    return {"total": total, "sealed": sealed, "draft": total - sealed, "lang_pairs": langs}
