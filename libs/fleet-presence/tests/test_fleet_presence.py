import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import fleet_presence as fp


def test_standalone_noop_without_store(tmp_path, monkeypatch):
    monkeypatch.delenv("WILLOW_STORE_ROOT", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))  # no ~/.willow/store here
    assert fp.announce("solo-app", "runs with zero backend") is False
    assert fp.roster() == []


def test_announce_and_roster(tmp_path):
    root = str(tmp_path / "store")
    assert fp.announce("the-nightstand", "3 down, 1 heavy", {"down": 3, "heavy": 1}, store_root=root)
    assert fp.announce("oakenscrolls-office", "7 graded, brier 0.16", {"graded": 7}, store_root=root)
    r = fp.roster(store_root=root)
    ids = {a["app_id"] for a in r}
    assert ids == {"the-nightstand", "oakenscrolls-office"}
    ns = next(a for a in r if a["app_id"] == "the-nightstand")
    assert ns["counts"]["down"] == 3 and ns["summary"] == "3 down, 1 heavy"


def test_reannounce_updates_in_place(tmp_path):
    root = str(tmp_path / "store")
    fp.announce("app", "v1", {"n": 1}, store_root=root)
    fp.announce("app", "v2", {"n": 2}, store_root=root)
    r = fp.roster(store_root=root)
    assert len(r) == 1 and r[0]["summary"] == "v2" and r[0]["counts"]["n"] == 2


def test_withdraw_is_soft_delete(tmp_path):
    root = str(tmp_path / "store")
    fp.announce("leaver", "here", store_root=root)
    assert fp.withdraw("leaver", store_root=root)
    assert fp.roster(store_root=root) == []
    # row kept, just flagged deleted — states-not-deletions
    db = Path(root) / "fleet" / "store.db"
    kept = sqlite3.connect(str(db)).execute(
        "SELECT deleted FROM records WHERE id='leaver'"
    ).fetchone()
    assert kept == (1,)


def test_content_leak_is_refused(tmp_path):
    root = str(tmp_path / "store")
    with pytest.raises(ValueError):
        fp.announce("bad", "ok", {"body": 1}, store_root=root)


def test_writes_willow_records_schema(tmp_path):
    """The atom must be readable as a willow record: data is json of the atom,
    with the exact columns willow's Store expects."""
    root = str(tmp_path / "store")
    fp.announce("schema-check", "s", {"x": 1}, store_root=root)
    db = Path(root) / "fleet" / "store.db"
    cols = {r[1] for r in sqlite3.connect(str(db)).execute("PRAGMA table_info(records)")}
    assert {"id", "data", "created_at", "updated_at", "deviation", "action", "deleted"} <= cols
    data = sqlite3.connect(str(db)).execute(
        "SELECT data FROM records WHERE id='schema-check'"
    ).fetchone()[0]
    assert json.loads(data)["app_id"] == "schema-check"
