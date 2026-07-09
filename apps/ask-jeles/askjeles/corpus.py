"""AskJeles' own verified-nugget corpus — storage and ranked lookup.

A nugget is a human-verified question/answer pair with citations:
{question, answer, sources, verified_by, verified_at, tags}.

Storage reuses the same SQLite shape as willow-mcp's SOIL `Store` (a
`records` table under `<collection>/store.db`, keyed by WILLOW_STORE_ROOT),
so nuggets written here are already visible to kb_search.py's soil scan
with no extra wiring, and the corpus stays readable by anything else that
understands a Willow-style SOIL collection.

This module has no MCP dependency — see corpus_server.py for the FastMCP
wrapper that exposes it as a standalone, MCP-agnostic server.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

NUGGETS_COLLECTION = "ask_jeles_corpus"
GAPS_COLLECTION = "ask_jeles_corpus_gaps"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
    id         TEXT PRIMARY KEY,
    data       TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_deleted ON records(deleted);
"""

_lock = threading.RLock()
_conns: dict[str, sqlite3.Connection] = {}


def _store_root() -> Path:
    return Path(os.environ.get("WILLOW_STORE_ROOT", str(Path.home() / ".willow" / "store"))).expanduser()


def _conn(collection: str) -> sqlite3.Connection:
    db_path = _store_root() / collection / "store.db"
    key = str(db_path)
    with _lock:
        if key not in _conns:
            db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(db_path), check_same_thread=False)
            conn.executescript(_SCHEMA)
            conn.commit()
            _conns[key] = conn
        return _conns[key]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _put(collection: str, record: dict[str, Any], record_id: str | None = None) -> str:
    rid = record_id or uuid.uuid4().hex[:8]
    now = _now()
    with _lock:
        conn = _conn(collection)
        existing = conn.execute("SELECT created_at FROM records WHERE id = ?", (rid,)).fetchone()
        created = existing[0] if existing else now
        conn.execute(
            "INSERT OR REPLACE INTO records (id, data, created_at, updated_at, deleted) "
            "VALUES (?, ?, ?, ?, 0)",
            (rid, json.dumps(record), created, now),
        )
        conn.commit()
    return rid


def _get(collection: str, record_id: str) -> dict[str, Any] | None:
    with _lock:
        row = _conn(collection).execute(
            "SELECT data, created_at, updated_at FROM records WHERE id = ? AND deleted = 0",
            (record_id,),
        ).fetchone()
    if not row:
        return None
    record = json.loads(row[0])
    record["_id"] = record_id
    record["_created"] = row[1]
    record["_updated"] = row[2]
    return record


def _all(collection: str) -> list[dict[str, Any]]:
    with _lock:
        rows = _conn(collection).execute(
            "SELECT id, data, created_at, updated_at FROM records "
            "WHERE deleted = 0 ORDER BY updated_at DESC"
        ).fetchall()
    out = []
    for rid, data, created, updated in rows:
        record = json.loads(data)
        record["_id"] = rid
        record["_created"] = created
        record["_updated"] = updated
        out.append(record)
    return out


_STOP = {
    "the", "and", "for", "with", "from", "that", "this", "these", "those",
    "have", "has", "had", "was", "were", "are", "is", "been", "being",
    "what", "who", "when", "where", "why", "how", "which", "would", "could",
    "should", "does", "did", "about", "into", "your", "you", "tell", "show",
    "find", "give", "please", "can", "will", "its", "it's",
}


def _tokens(text: str) -> list[str]:
    return [
        t for t in re.findall(r"[a-z0-9][a-z0-9_-]{2,}", (text or "").lower())
        if t not in _STOP
    ]


# ── Nuggets ──────────────────────────────────────────────────────────────


def put_nugget(
    question: str,
    answer: str,
    sources: list[str],
    verified_by: str,
    tags: list[str] | None = None,
    nugget_id: str | None = None,
    verified_at: str | None = None,
) -> dict[str, Any]:
    """Add or update a verified nugget. Returns {id, action} or {error}."""
    question = (question or "").strip()
    answer = (answer or "").strip()
    verified_by = (verified_by or "").strip()
    if not question or not answer or not verified_by:
        return {"error": "question, answer, and verified_by are required"}
    record = {
        "question": question,
        "answer": answer,
        "sources": [str(s) for s in (sources or [])],
        "verified_by": verified_by,
        "verified_at": verified_at or datetime.now(timezone.utc).date().isoformat(),
        "tags": [str(t) for t in (tags or [])],
        "status": "verified",
    }
    action = "updated" if (nugget_id and _get(NUGGETS_COLLECTION, nugget_id)) else "created"
    rid = _put(NUGGETS_COLLECTION, record, record_id=nugget_id)
    return {"id": rid, "action": action}


def get_nugget(nugget_id: str) -> dict[str, Any]:
    return _get(NUGGETS_COLLECTION, nugget_id) or {"error": "not_found"}


def list_nuggets(limit: int = 50) -> list[dict[str, Any]]:
    return _all(NUGGETS_COLLECTION)[: max(0, limit)]


def _score(nugget: dict[str, Any], query_tokens: list[str]) -> float:
    if not query_tokens:
        return 0.0
    question = (nugget.get("question") or "").lower()
    answer = (nugget.get("answer") or "").lower()
    tags = " ".join(nugget.get("tags") or []).lower()
    q_tokens = set(_tokens(question))
    matched = sum(1 for t in query_tokens if t in q_tokens)
    score = matched / len(query_tokens)
    if set(query_tokens) == q_tokens:
        score += 1.0
    elif matched == len(query_tokens):
        score += 0.5
    if any(t in answer for t in query_tokens):
        score += 0.1
    if any(t in tags for t in query_tokens):
        score += 0.1
    return score


MIN_ASK_SCORE = 0.5  # below this, a "match" is too weak to answer with — treat as a gap


def _ranked(query: str, limit: int) -> list[tuple[dict[str, Any], float]]:
    tokens = _tokens(query)
    if not tokens:
        return []
    scored = [(n, _score(n, tokens)) for n in _all(NUGGETS_COLLECTION)]
    scored = [(n, s) for n, s in scored if s > 0]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored[: max(0, limit)]


def search_nuggets(query: str, limit: int = 8) -> list[dict[str, Any]]:
    """Ranked nugget search. Pure lookup — never logs a gap on a miss.

    Question-token overlap is weighted highest so a near-exact question
    match outranks a nugget that merely mentions the query in its answer.
    """
    return [n for n, _ in _ranked(query, limit)]


def ask_corpus(question: str) -> dict[str, Any]:
    """The spec's interaction flow: exact match, else best partial match,
    else 'I don't know yet' — which logs the gap for later triage.

    Unlike search_nuggets(), this is the deliberate "ask the corpus"
    entrypoint (used by corpus_server's corpus_ask tool and Jeles'
    synthesize step), so a miss — or a match too weak to trust — is
    assumed to be a real gap worth tracking, not background search noise.
    """
    ranked = _ranked(question, 5)
    if not ranked or ranked[0][1] < MIN_ASK_SCORE:
        log_gap(question)
        return {"found": False, "nugget": None, "candidates": [n for n, _ in ranked]}
    tokens = set(_tokens(question))
    top, _top_score = ranked[0]
    top_tokens = set(_tokens(top.get("question") or ""))
    exact = bool(tokens) and tokens == top_tokens
    return {"found": True, "exact": exact, "nugget": top, "candidates": [n for n, _ in ranked[1:]]}


def to_search_hit(nugget: dict[str, Any], idx: int = 0) -> dict[str, Any]:
    """Shape a nugget as a search hit compatible with askjeles/search.py's
    flatten_results()/rank_hit() pipeline (source_id="corpus")."""
    sources = nugget.get("sources") or []
    return {
        "title": nugget.get("question") or "Verified nugget",
        "url": sources[0] if sources else "",
        "snippet": nugget.get("answer") or "",
        "source": f"Verified corpus — {nugget.get('verified_by') or 'unknown'}",
        "date": nugget.get("verified_at") or "",
        "source_id": "corpus",
        "hostname": "corpus.local",
        "confidence": "verified",
        "nugget_id": nugget.get("_id") or "",
        "verified_by": nugget.get("verified_by") or "",
        "verified_at": nugget.get("verified_at") or "",
        "extra_sources": sources,
        "tags": nugget.get("tags") or [],
        "n": idx,
    }


# ── Gaps ("I don't know yet") ───────────────────────────────────────────


def log_gap(question: str) -> dict[str, Any]:
    """Log an unanswered question. Repeated asks bump asked_count instead of
    creating duplicates, keyed by the question's normalized token set."""
    question = (question or "").strip()
    if not question:
        return {"error": "question required"}
    tokens = tuple(sorted(set(_tokens(question))))
    key = "|".join(tokens) or question.lower()
    gap_id = uuid.uuid5(uuid.NAMESPACE_URL, key).hex[:12]
    existing = _get(GAPS_COLLECTION, gap_id)
    record = {
        "question": question,
        "status": "unverified",
        "asked_count": (existing or {}).get("asked_count", 0) + 1,
        "first_asked_at": (existing or {}).get("first_asked_at") or _now(),
        "last_asked_at": _now(),
    }
    rid = _put(GAPS_COLLECTION, record, record_id=gap_id)
    return {"id": rid, "asked_count": record["asked_count"]}


def list_gaps(limit: int = 50) -> list[dict[str, Any]]:
    gaps = _all(GAPS_COLLECTION)
    gaps.sort(key=lambda g: g.get("asked_count", 0), reverse=True)
    return gaps[: max(0, limit)]
