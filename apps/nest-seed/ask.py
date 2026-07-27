"""
nest-seed/ask.py — ask-your-Nest semantic search.

A tiny local retrieval layer: embed a natural-language question and cosine-rank
the Nest's content fragments against it. The query is embedded with the
`search_query:` prefix and fragments with `search_document:` (per embed.py), the
asymmetry nomic needs.

The DB is canonical and never mutated by consumers, so the per-fragment vector
index lives in a sidecar next to it. The index is incremental — only new
fragments are embedded on subsequent runs.
"""
from __future__ import annotations

import json
import os
import sqlite3

from nest_pipeline import embed as _embed  # shared Nest pipeline core (box audit A4)

# Searchable = meaningful content; skip date/person/photo (tiny tokens).
SEARCHABLE = ("document", "note", "event", "location", "receipt", "secret")


def _index_path(db_path: str, model: str) -> str:
    safe = model.replace("/", "_").replace(":", "_")
    return f"{db_path}.ask_{safe}.json"


def _load_index(db_path: str, model: str) -> dict[str, list[float]]:
    p = _index_path(db_path, model)
    if not os.path.exists(p):
        return {}
    try:
        return json.loads(open(p).read())
    except (OSError, ValueError):
        return {}


def _save_index(db_path: str, model: str, idx: dict) -> None:
    try:
        open(_index_path(db_path, model), "w").write(json.dumps(idx))
    except OSError:
        pass


def build_index(db_path: str, model: str = _embed.DEFAULT_EMBED_MODEL,
                rebuild: bool = False, verbose: bool = False) -> dict:
    """Embed all searchable fragments (incrementally) into the sidecar index."""
    if not _embed.available(model):
        return {"status": "skipped", "reason": f"embedder unavailable ({model})"}
    idx = {} if rebuild else _load_index(db_path, model)
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        f"select id, content from fragments where fragment_type in "
        f"({','.join('?' for _ in SEARCHABLE)}) and length(content) >= 12",
        SEARCHABLE,
    ).fetchall()
    conn.close()

    added = 0
    for fid, content in rows:
        key = str(fid)
        if key in idx:
            continue
        vec = _embed.embed_document(content, model=model)
        if vec:
            idx[key] = vec
            added += 1
    _save_index(db_path, model, idx)
    return {"status": "ok", "indexed": len(idx), "added": added, "candidates": len(rows)}


def ask(db_path: str, query: str, k: int = 8,
        model: str = _embed.DEFAULT_EMBED_MODEL,
        rebuild: bool = False) -> dict:
    """Return the top-k fragments most semantically similar to `query`."""
    build = build_index(db_path, model, rebuild=rebuild)
    if build["status"] != "ok":
        return build
    idx = _load_index(db_path, model)
    qv = _embed.embed_query(query, model=model)
    if not qv:
        return {"status": "skipped", "reason": "query embedding failed"}

    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "select f.id, f.fragment_type, f.label, f.content, s.filename "
        "from fragments f join sources s on s.id = f.source_id "
        f"where f.fragment_type in ({','.join('?' for _ in SEARCHABLE)})",
        SEARCHABLE,
    ).fetchall()
    conn.close()

    scored = []
    for fid, ftype, label, content, filename in rows:
        v = idx.get(str(fid))
        if not v:
            continue
        scored.append((_embed.cosine(qv, v), ftype, label, content, filename))
    scored.sort(key=lambda t: t[0], reverse=True)

    hits = [{
        "score": round(s, 4), "fragment_type": ft, "label": lb,
        "source": fn, "snippet": (c or "")[:200],
    } for s, ft, lb, c, fn in scored[:k]]
    return {"status": "ok", "query": query, "indexed": len(idx), "hits": hits}
