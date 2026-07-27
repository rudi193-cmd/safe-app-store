"""Tests for bridge.py — run from inside apps/nest-seed/, no Ollama.

The bridge's contract is PII-safety: it must emit structure (counts, category
names, secret kinds) and NEVER fragment content, filenames, person names, or
secret values. These tests assert that boundary directly.
"""
import json

from nest_pipeline import db as _db
from nest_pipeline import selflearn as _learn
import bridge as _bridge

_MODEL = "nomic-embed-text"
_SECRET_PII = "Mqqqqqqqqqqqqqqqqqqqqqqqq.aB3dEf.zzzzzzzzzzzzzz"  # synthetic
_PERSON = "Jane Defendant"
_FILENAME = "custody_agreement_2021.pdf"


def _mk(tmp_path, monkeypatch):
    monkeypatch.setenv("NEST_CACHE_DIR", str(tmp_path / "cache"))
    p = tmp_path / "t.db"
    conn = _db.open_db(p)
    _db.init_meta(conn, "Tester")
    conn.execute("insert into sources(path,filename,file_hash) values(?,?,?)",
                 (f"/x/{_FILENAME}", _FILENAME, "h1"))
    conn.executemany(
        "insert into fragments(source_id,fragment_type,content,label,confidence) values(?,?,?,?,?)",
        [(1, "document", "secret legal custody filing text", "legal", "likely"),
         (1, "document", "another legal filing here", "legal", "likely"),
         (1, "note", "a reading list note", "knowledge", "likely"),
         (1, "person", _PERSON, "", "likely"),
         (1, "secret", "[REDACTED:discord_token]", "discord_token", "confirmed")])
    conn.commit()
    conn.close()
    return str(p)


def test_bridge_summarises_structure(tmp_path, monkeypatch):
    db = _mk(tmp_path, monkeypatch)
    res = _bridge.build_bridge(db, _MODEL)
    assert res["status"] == "ok"
    assert res["owner"] == "Tester" and res["sources"] == 1
    titles = [a["title"] for a in res["atoms"]]
    assert any(t.startswith("Nest structure") for t in titles)
    assert any("legal" in t for t in titles)
    assert any("security" in t.lower() for t in titles)
    # category atom carries the count
    legal = next(a for a in res["atoms"] if a["title"].endswith("legal"))
    assert "2 fragments" in legal["summary"]


def test_bridge_emits_no_pii(tmp_path, monkeypatch):
    db = _mk(tmp_path, monkeypatch)
    res = _bridge.build_bridge(db, _MODEL)
    blob = json.dumps(res)
    # never leak content, secret values, person names, or filenames
    assert _SECRET_PII not in blob
    assert "custody filing text" not in blob
    assert _PERSON not in blob
    assert _FILENAME not in blob
    # but the secret KIND is surfaced so the fleet knows to flag rotation
    assert "discord_token" in blob


def test_write_manifest_creates_sidecar(tmp_path, monkeypatch):
    db = _mk(tmp_path, monkeypatch)
    res = _bridge.write_manifest(db, _MODEL)
    assert res["manifest"] == f"{db}.bridge.json"
    on_disk = json.loads(open(res["manifest"]).read())
    assert on_disk["atoms"] and on_disk["owner"] == "Tester"
