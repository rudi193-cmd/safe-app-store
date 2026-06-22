"""Tests for ask.py — run from inside apps/nest-seed/, no Ollama."""
import db as _db
import embed as _embed
import ask as _ask

_VOCAB = ["legal", "school", "money", "weather"]


def _vec(text):
    low = text.lower()
    v = [float(low.count(w)) for w in _VOCAB]
    return v if any(v) else [1.0, 1.0, 1.0, 1.0]


def _mk(tmp_path, monkeypatch):
    monkeypatch.setattr(_embed, "available", lambda model=None: True)
    monkeypatch.setattr(_embed, "embed_document", lambda t, model=None: _vec(t))
    monkeypatch.setattr(_embed, "embed_query", lambda t, model=None: _vec(t))
    p = tmp_path / "t.db"
    conn = _db.open_db(p)
    _db.init_meta(conn, "T")
    conn.execute("insert into sources(path,filename,file_hash) values('/a','court.md','h1')")
    conn.execute("insert into sources(path,filename,file_hash) values('/b','class.md','h2')")
    conn.executemany(
        "insert into fragments(source_id,fragment_type,content,label,confidence) values(?,?,?,?,?)",
        [(1, "document", "legal custody filing and court motion legal", "legal", "likely"),
         (2, "document", "school lesson plan for the classroom school", "education", "likely")])
    conn.commit()
    conn.close()
    return str(p)


def test_build_index_then_ask_ranks_relevant_first(tmp_path, monkeypatch):
    db = _mk(tmp_path, monkeypatch)
    bi = _ask.build_index(db)
    assert bi["status"] == "ok" and bi["added"] == 2

    res = _ask.ask(db, "school classroom teaching")
    assert res["status"] == "ok"
    assert res["hits"][0]["source"] == "class.md"
    assert res["hits"][0]["label"] == "education"


def test_index_is_incremental(tmp_path, monkeypatch):
    db = _mk(tmp_path, monkeypatch)
    _ask.build_index(db)
    again = _ask.build_index(db)
    assert again["added"] == 0  # nothing new to embed


def test_ask_graceful_when_embedder_down(tmp_path, monkeypatch):
    db = _mk(tmp_path, monkeypatch)
    monkeypatch.setattr(_embed, "available", lambda model=None: False)
    res = _ask.ask(db, "anything")
    assert res["status"] == "skipped"
