"""Tests for the willow_read seam — run without any Willow store present.

The seam prefers an injected knowledge_search client (rule #1) and falls back to
a direct read of Willow's local store.db only when no client is injected. It must
never raise out of search().
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from app import willow_read as wr  # noqa: E402


class FakeClient:
    def __init__(self, atoms):
        self.atoms = atoms
        self.calls = []

    def knowledge_search(self, query, limit):
        self.calls.append((query, limit))
        return self.atoms


class BoomClient:
    def knowledge_search(self, query, limit):
        raise RuntimeError("kb down")


def setup_function(_):
    wr.set_client(None)


def teardown_function(_):
    wr.set_client(None)


def test_injected_client_preferred(tmp_path, monkeypatch):
    # even if a store.db existed, the injected client wins
    monkeypatch.setenv("WILLOW_STORE_ROOT", str(tmp_path))
    atoms = [{"content": "a", "domain": "d"}, {"content": "b", "domain": "d"}]
    fake = FakeClient(atoms)
    wr.set_client(fake)
    assert wr.active_backend() == "mcp"
    assert wr.search("q", 10) == atoms
    assert fake.calls == [("q", 10)]


def test_client_arg_beats_module_level():
    wr.set_client(FakeClient([{"content": "module"}]))
    got = wr.search("q", client=FakeClient([{"content": "arg"}]))
    assert got == [{"content": "arg"}]


def test_client_non_dict_atoms_filtered():
    wr.set_client(FakeClient([{"content": "ok"}, "junk", 42, None]))
    assert wr.search("q") == [{"content": "ok"}]


def test_raising_client_degrades_to_empty():
    wr.set_client(BoomClient())
    assert wr.search("q") == []  # never propagates


def test_no_client_no_store_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("WILLOW_STORE_ROOT", str(tmp_path))  # no store.db here
    assert wr.active_backend() == "none"
    assert wr.available() is False
    assert wr.search("q") == []


def test_sqlite_fallback_reads_store(tmp_path, monkeypatch):
    import json
    import sqlite3

    monkeypatch.setenv("WILLOW_STORE_ROOT", str(tmp_path))
    db = tmp_path / "knowledge" / "store.db"
    db.parent.mkdir(parents=True)
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE records (data TEXT, deleted INTEGER DEFAULT 0)")
    conn.execute("INSERT INTO records (data, deleted) VALUES (?, 0)",
                 (json.dumps({"content": "medicare budget line"}),))
    conn.execute("INSERT INTO records (data, deleted) VALUES (?, 1)",
                 (json.dumps({"content": "medicare deleted"}),))
    conn.commit()
    conn.close()

    assert wr.active_backend() == "sqlite"
    hits = wr.search("medicare", 10)
    assert {"content": "medicare budget line"} in hits
    assert {"content": "medicare deleted"} not in hits  # deleted=1 excluded


def test_sqlite_fallback_never_raises_on_bad_db(tmp_path, monkeypatch):
    monkeypatch.setenv("WILLOW_STORE_ROOT", str(tmp_path))
    db = tmp_path / "knowledge" / "store.db"
    db.parent.mkdir(parents=True)
    db.write_text("not a database")  # corrupt
    assert wr.search("q") == []  # degrades, no exception
