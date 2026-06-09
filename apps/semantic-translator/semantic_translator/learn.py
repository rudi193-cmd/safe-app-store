"""Flashcard study session — sources corpus pairs and Jeles atoms."""
from __future__ import annotations

import json
import pathlib
from datetime import datetime, timezone

from . import db

_CORPUS = pathlib.Path("data/corpus.jsonl")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── card seeding ─────────────────────────────────────────────────────────────

def _load_bilingual_pairs() -> list[dict]:
    """Return (front=EN, back=ES) pairs from bilingual lessons in corpus."""
    if not _CORPUS.exists():
        return []
    by_lesson: dict[str, list[dict]] = {}
    with open(_CORPUS, encoding="utf-8") as f:
        for line in f:
            seg = json.loads(line)
            if seg.get("is_bilingual"):
                by_lesson.setdefault(seg["lesson"], []).append(seg)

    pairs = []
    for lesson, segs in by_lesson.items():
        en_segs = [s for s in segs if s["lang"] == "en"]
        es_segs = [s for s in segs if s["lang"] == "es"]
        for i, en in enumerate(en_segs):
            es = es_segs[i] if i < len(es_segs) else None
            pairs.append({
                "atom_id": en["id"],
                "front": en["text"],
                "back": es["text"] if es else "",
                "lesson": lesson,
                "lang_front": "en",
                "lang_back": "es",
                "source": "bilingual",
            })
    return pairs


def _load_jeles_atoms() -> list[dict]:
    """Return flashcards from Jeles atoms that passed the gate (ingest_log)."""
    log = pathlib.Path("data/ingest_log.jsonl")
    if not log.exists() or not _CORPUS.exists():
        return []

    # index corpus by id
    corpus_idx: dict[str, dict] = {}
    with open(_CORPUS, encoding="utf-8") as f:
        for line in f:
            seg = json.loads(line)
            corpus_idx[seg["id"]] = seg

    cards = []
    with open(log, encoding="utf-8") as f:
        for line in f:
            entry = json.loads(line)
            if entry.get("blocked") or entry.get("error"):
                continue
            seg_id = entry.get("seg_id", "")
            atom_id = (entry.get("result") or {}).get("id", seg_id)
            seg = corpus_idx.get(seg_id)
            if not seg:
                continue
            cards.append({
                "atom_id": atom_id,
                "front": seg["text"],
                "back": "",          # no ES equivalent yet — shows concept only
                "lesson": seg["lesson"],
                "lang_front": seg["lang"],
                "lang_back": "es" if seg["lang"] == "en" else "en",
                "source": "jeles",
            })
    return cards


def seed_cards(learner_id: str) -> int:
    """Create SRS cards for a learner from all available content. Returns new card count."""
    db.init_db()
    learner = db.get_learner(learner_id)
    if not learner:
        raise ValueError(f"Unknown learner: {learner_id}")

    all_content = _load_bilingual_pairs() + _load_jeles_atoms()
    new_count = 0
    seen: set[str] = set()

    with db.get_db() as conn:
        existing = {
            r[0] for r in conn.execute(
                "SELECT atom_id FROM cards WHERE learner_id=?", (learner_id,)
            )
        }

    for item in all_content:
        atom_id = item["atom_id"]
        if atom_id in existing or atom_id in seen:
            continue
        seen.add(atom_id)
        db.get_or_create_card(learner_id, atom_id)
        new_count += 1

    return new_count


# ── study session ─────────────────────────────────────────────────────────────

def get_study_queue(learner_id: str, limit: int = 20) -> list[dict]:
    """
    Return due SRS cards enriched with corpus content for display.
    Falls back to new (unseen) cards if nothing is due.
    """
    db.init_db()
    due = db.get_due_cards(learner_id, limit=limit)

    # If nothing due, pull new cards (state=1=Learning, reps=0 implied by card_json={})
    if not due:
        with db.get_db() as conn:
            due = [dict(r) for r in conn.execute(
                "SELECT * FROM cards WHERE learner_id=? AND card_json='{}' LIMIT ?",
                (learner_id, limit),
            )]

    if not due:
        return []

    # Enrich with corpus content
    content_map = _build_content_map()
    enriched = []
    for card in due:
        content = content_map.get(card["atom_id"], {})
        enriched.append({**card, **content})
    return enriched


def _build_content_map() -> dict[str, dict]:
    """Map atom_id → {front, back, lesson, source} from all sources."""
    result: dict[str, dict] = {}
    for item in _load_bilingual_pairs():
        result[item["atom_id"]] = item
    for item in _load_jeles_atoms():
        if item["atom_id"] not in result:
            result[item["atom_id"]] = item
    return result


def submit_rating(learner_id: str, atom_id: str, rating_int: int) -> dict:
    """
    Submit an SRS rating (1=Again, 2=Hard, 3=Good, 4=Easy).
    Returns updated card.
    """
    from fsrs import Card, Rating, Scheduler  # type: ignore
    import json as _json

    row = db.get_or_create_card(learner_id, atom_id)
    card_dict = _json.loads(row["card_json"]) if row["card_json"] and row["card_json"] != "{}" else None
    card = Card.from_dict(card_dict) if card_dict else Card()

    rating = Rating(rating_int)
    card, _ = Scheduler().review_card(card, rating)

    db.update_card(row["id"], card_json=card.to_json(), due=card.due.isoformat())
    db.create_review_event(row["id"], learner_id, rating_int, source="flashcard")
    return db.get_or_create_card(learner_id, atom_id)


def study_stats(learner_id: str) -> dict:
    """Return stats for display in the Learn tab header."""
    base = db.card_stats(learner_id)
    with db.get_db() as conn:
        today_start = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00")
        studied_today = conn.execute(
            "SELECT COUNT(*) FROM review_events WHERE learner_id=? AND created_at>=?",
            (learner_id, today_start),
        ).fetchone()[0]
        new_cards = conn.execute(
            "SELECT COUNT(*) FROM cards WHERE learner_id=? AND card_json='{}'",
            (learner_id,),
        ).fetchone()[0]
    return {**base, "studied_today": studied_today, "new": new_cards}
