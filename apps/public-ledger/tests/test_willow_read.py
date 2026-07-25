"""Tests for the willow_read seam.

The seam reads the KB ONLY through an injected knowledge_search client (rule #1).
The raw direct read of Willow's shared store.db was removed (box audit B3 — the
records table has no per-app scope column, so a raw read leaked every app's
atoms). With no client injected the seam returns [] and never touches the store.
It must never raise out of search().
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


def test_present_store_is_not_read_without_a_client(tmp_path, monkeypatch):
    # box audit B3: even with a populated shared store.db present and NO gated
    # client, the seam must NOT read it — that raw read leaked every app's atoms.
    import json
    import sqlite3

    monkeypatch.setenv("WILLOW_STORE_ROOT", str(tmp_path))
    db = tmp_path / "knowledge" / "store.db"
    db.parent.mkdir(parents=True)
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE records (data TEXT, deleted INTEGER DEFAULT 0)")
    conn.execute("INSERT INTO records (data, deleted) VALUES (?, 0)",
                 (json.dumps({"content": "medicare budget line"}),))
    conn.commit()
    conn.close()

    assert wr.active_backend() == "none"      # store present, but no gated backend
    assert wr.available() is False
    assert wr.search("medicare", 10) == []    # the shared store is never touched
