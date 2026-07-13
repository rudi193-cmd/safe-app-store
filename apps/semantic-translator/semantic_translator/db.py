"""SQLite persistence — documents, segments, verifications, SRS cards."""
from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path("data/translator.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    source_path TEXT DEFAULT '',
    source_lang TEXT NOT NULL DEFAULT 'en',
    target_lang TEXT NOT NULL DEFAULT 'es',
    status      TEXT NOT NULL DEFAULT 'pending_review',
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS segments (
    id          TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id),
    position    INTEGER NOT NULL,
    source_text TEXT NOT NULL,
    candidate   TEXT DEFAULT '',
    jeles_score REAL DEFAULT 0.0,
    atom_id     TEXT DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'pending',
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS learners (
    id                TEXT PRIMARY KEY,
    name              TEXT NOT NULL,
    native_lang       TEXT NOT NULL DEFAULT 'en',
    target_lang       TEXT NOT NULL DEFAULT 'es',
    calibration_score REAL NOT NULL DEFAULT 1.0,
    created_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS verifications (
    id          TEXT PRIMARY KEY,
    segment_id  TEXT NOT NULL REFERENCES segments(id),
    learner_id  TEXT NOT NULL REFERENCES learners(id),
    verdict     TEXT NOT NULL,
    correction  TEXT DEFAULT '',
    weight      REAL NOT NULL DEFAULT 1.0,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cards (
    id          TEXT PRIMARY KEY,
    learner_id  TEXT NOT NULL REFERENCES learners(id),
    atom_id     TEXT NOT NULL,
    card_json   TEXT NOT NULL DEFAULT '{}',
    due         TEXT NOT NULL,
    UNIQUE(learner_id, atom_id)
);

CREATE TABLE IF NOT EXISTS review_events (
    id         TEXT PRIMARY KEY,
    card_id    TEXT NOT NULL REFERENCES cards(id),
    learner_id TEXT NOT NULL REFERENCES learners(id),
    rating     INTEGER NOT NULL,
    source     TEXT NOT NULL DEFAULT 'verification',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_segments_document ON segments(document_id);
CREATE INDEX IF NOT EXISTS idx_segments_status   ON segments(status);
CREATE INDEX IF NOT EXISTS idx_verifications_seg ON verifications(segment_id);
CREATE INDEX IF NOT EXISTS idx_cards_due         ON cards(learner_id, due);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uid() -> str:
    return str(uuid.uuid4())


@contextmanager
def get_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with get_db() as conn:
        conn.executescript(SCHEMA)


# --- Documents ---

def create_document(title: str, source_lang: str = "en", target_lang: str = "es",
                    source_path: str = "") -> dict:
    doc = dict(id=_uid(), title=title, source_path=source_path,
               source_lang=source_lang, target_lang=target_lang,
               status="pending_review", created_at=_now())
    with get_db() as conn:
        conn.execute(
            "INSERT INTO documents VALUES (:id,:title,:source_path,:source_lang,:target_lang,:status,:created_at)",
            doc,
        )
    return doc


def get_document(doc_id: str) -> dict | None:
    with get_db() as conn:
        r = conn.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
        return dict(r) if r else None


def list_documents() -> list[dict]:
    with get_db() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM documents ORDER BY created_at DESC"
        )]


def update_document_status(doc_id: str, status: str) -> None:
    with get_db() as conn:
        conn.execute("UPDATE documents SET status=? WHERE id=?", (status, doc_id))


# --- Segments ---

def create_segment(document_id: str, position: int, source_text: str,
                   candidate: str = "", jeles_score: float = 0.0,
                   atom_id: str = "") -> dict:
    seg = dict(id=_uid(), document_id=document_id, position=position,
               source_text=source_text, candidate=candidate,
               jeles_score=jeles_score, atom_id=atom_id,
               status="pending", created_at=_now())
    with get_db() as conn:
        conn.execute(
            "INSERT INTO segments VALUES (:id,:document_id,:position,:source_text,:candidate,:jeles_score,:atom_id,:status,:created_at)",
            seg,
        )
    return seg


def get_segment(seg_id: str) -> dict | None:
    with get_db() as conn:
        r = conn.execute("SELECT * FROM segments WHERE id=?", (seg_id,)).fetchone()
        return dict(r) if r else None


def get_segments(document_id: str) -> list[dict]:
    with get_db() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM segments WHERE document_id=? ORDER BY position",
            (document_id,),
        )]


def update_segment(seg_id: str, **kwargs) -> None:
    if not kwargs:
        return
    cols = ", ".join(f"{k}=?" for k in kwargs)
    with get_db() as conn:
        conn.execute(f"UPDATE segments SET {cols} WHERE id=?", (*kwargs.values(), seg_id))


def get_pending_segments(limit: int = 20) -> list[dict]:
    """Uncertain segments first (lowest jeles_score = most needs review)."""
    with get_db() as conn:
        return [dict(r) for r in conn.execute(
            """SELECT s.*, d.title AS doc_title, d.source_lang, d.target_lang
               FROM segments s JOIN documents d ON s.document_id = d.id
               WHERE s.status IN ('pending', 'in_review', 'needs_native')
               ORDER BY s.jeles_score ASC
               LIMIT ?""",
            (limit,),
        )]


def pending_count() -> int:
    with get_db() as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM segments WHERE status IN ('pending','in_review')"
        ).fetchone()[0]


# --- Learners ---

def create_learner(name: str, native_lang: str = "en", target_lang: str = "es") -> dict:
    learner = dict(id=_uid(), name=name, native_lang=native_lang,
                   target_lang=target_lang, calibration_score=1.0, created_at=_now())
    with get_db() as conn:
        conn.execute(
            "INSERT INTO learners VALUES (:id,:name,:native_lang,:target_lang,:calibration_score,:created_at)",
            learner,
        )
    return learner


def get_learner(learner_id: str) -> dict | None:
    with get_db() as conn:
        r = conn.execute("SELECT * FROM learners WHERE id=?", (learner_id,)).fetchone()
        return dict(r) if r else None


def list_learners() -> list[dict]:
    with get_db() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM learners ORDER BY name")]


def update_calibration(learner_id: str, score: float) -> None:
    with get_db() as conn:
        conn.execute("UPDATE learners SET calibration_score=? WHERE id=?", (score, learner_id))


# --- Verifications ---

def create_verification(segment_id: str, learner_id: str, verdict: str,
                        correction: str = "", weight: float = 1.0) -> dict:
    v = dict(id=_uid(), segment_id=segment_id, learner_id=learner_id,
             verdict=verdict, correction=correction, weight=weight, created_at=_now())
    with get_db() as conn:
        conn.execute(
            "INSERT INTO verifications VALUES (:id,:segment_id,:learner_id,:verdict,:correction,:weight,:created_at)",
            v,
        )
    return v


def get_verifications(segment_id: str) -> list[dict]:
    with get_db() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM verifications WHERE segment_id=? ORDER BY created_at",
            (segment_id,),
        )]


# --- Cards (SRS) ---

def get_or_create_card(learner_id: str, atom_id: str) -> dict:
    with get_db() as conn:
        r = conn.execute(
            "SELECT * FROM cards WHERE learner_id=? AND atom_id=?",
            (learner_id, atom_id),
        ).fetchone()
        if r:
            return dict(r)
        now = _now()
        card = dict(id=_uid(), learner_id=learner_id, atom_id=atom_id,
                    card_json="{}", due=now)
        conn.execute(
            "INSERT INTO cards VALUES (:id,:learner_id,:atom_id,:card_json,:due)",
            card,
        )
        return card


def update_card(card_id: str, card_json: str, due: str) -> None:
    with get_db() as conn:
        conn.execute("UPDATE cards SET card_json=?, due=? WHERE id=?",
                     (card_json, due, card_id))


def get_due_cards(learner_id: str, limit: int = 20) -> list[dict]:
    now = _now()
    with get_db() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM cards WHERE learner_id=? AND due<=? ORDER BY due LIMIT ?",
            (learner_id, now, limit),
        )]


def card_stats(learner_id: str) -> dict:
    now = _now()
    with get_db() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM cards WHERE learner_id=?", (learner_id,)
        ).fetchone()[0]
        due_count = conn.execute(
            "SELECT COUNT(*) FROM cards WHERE learner_id=? AND due<=?", (learner_id, now)
        ).fetchone()[0]
    return {"total": total, "due": due_count}


# --- Review Events ---

def create_review_event(card_id: str, learner_id: str, rating: int,
                        source: str = "verification") -> dict:
    ev = dict(id=_uid(), card_id=card_id, learner_id=learner_id,
              rating=rating, source=source, created_at=_now())
    with get_db() as conn:
        conn.execute(
            "INSERT INTO review_events VALUES (:id,:card_id,:learner_id,:rating,:source,:created_at)",
            ev,
        )
    return ev
