"""Tests for curate.py — run from inside apps/nest-seed/, no Ollama.

NEST_CACHE_DIR is pointed at tmp so the discovered store is isolated per test.
"""
from nest_pipeline import db as _db
from nest_pipeline import selflearn as _learn
import curate as _curate

_MODEL = "nomic-embed-text"


def _mk(tmp_path, monkeypatch):
    monkeypatch.setenv("NEST_CACHE_DIR", str(tmp_path / "cache"))
    p = tmp_path / "t.db"
    conn = _db.open_db(p)
    _db.init_meta(conn, "Tester")
    conn.execute("insert into sources(path,filename,file_hash) values('/a','a.md','h1')")
    conn.executemany(
        "insert into fragments(source_id,fragment_type,content,label,confidence) values(?,?,?,?,?)",
        [(1, "document", "exported boilerplate one", "auto:seed-version-1-0", "likely"),
         (1, "document", "exported boilerplate two", "auto:seed-version-1-0", "likely"),
         (1, "note", "a verdict benchmark thing", "auto:benchmark-verdict", "likely")])
    conn.commit()
    conn.close()
    _learn.save_discovered(_MODEL, {
        "auto:seed-version-1-0": {"vec": [0.1, 0.2], "label": "seed v1", "size": 28, "cohesion": 0.6},
        "auto:benchmark-verdict": {"vec": [0.3, 0.4], "label": "verdicts", "size": 6, "cohesion": 0.84},
    })
    return str(p)


def test_list_categories_merges_store_and_db(tmp_path, monkeypatch):
    db = _mk(tmp_path, monkeypatch)
    res = _curate.list_categories(db, _MODEL)
    assert res["count"] == 2
    by_name = {c["name"]: c for c in res["categories"]}
    assert by_name["auto:seed-version-1-0"]["db_fragments"] == 2
    assert by_name["auto:benchmark-verdict"]["db_fragments"] == 1
    # sorted by size desc
    assert res["categories"][0]["name"] == "auto:seed-version-1-0"


def test_rename_updates_store_and_relabels_db(tmp_path, monkeypatch):
    db = _mk(tmp_path, monkeypatch)
    res = _curate.rename_category(db, "auto:benchmark-verdict", "court-rulings", _MODEL)
    assert res["status"] == "ok"
    assert res["new"] == "auto:court-rulings"  # kept under the auto: namespace
    assert res["fragments_relabelled"] == 1
    disc = _learn.load_discovered(_MODEL)
    assert "auto:court-rulings" in disc and "auto:benchmark-verdict" not in disc
    counts = _curate._db_label_counts(db)
    assert counts.get("auto:court-rulings") == 1 and "auto:benchmark-verdict" not in counts


def test_rename_unknown_category_errors(tmp_path, monkeypatch):
    db = _mk(tmp_path, monkeypatch)
    res = _curate.rename_category(db, "auto:nope", "whatever", _MODEL)
    assert res["status"] == "error"


def test_prune_drops_store_and_clears_labels(tmp_path, monkeypatch):
    db = _mk(tmp_path, monkeypatch)
    res = _curate.prune_category(db, "auto:seed-version-1-0", _MODEL)
    assert res["status"] == "ok"
    assert res["fragments_cleared"] == 2
    assert "auto:seed-version-1-0" not in _learn.load_discovered(_MODEL)
    counts = _curate._db_label_counts(db)
    assert "auto:seed-version-1-0" not in counts
