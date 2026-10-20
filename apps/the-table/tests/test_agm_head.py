"""the-table -- test_agm_head.py (J9, box-build SPEC R9).

``agm_head.read`` recomputes campaign.db's head with ai-game-master's own
``verify_ledger.py``: read / broken / unreachable, never collapsed. A broken
or unreachable ledger is never anchored.
"""
from __future__ import annotations

import importlib.util
import os
import shutil
import sqlite3
import sys
import tempfile
from types import SimpleNamespace

import pytest

_APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _APP_ROOT)

from the_table import agm_head

_AGM = os.path.join(os.path.dirname(_APP_ROOT), "ai-game-master")


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _row_hash(*args):
    return agm_head._verify_ledger().row_hash(*args)


@pytest.fixture
def ledger():
    """A campaign.db written by ai-game-master's OWN code: its schema files,
    and its writer (``docs/poc_vander_room.py`` ``append_turn``), loaded by
    path. agm_head anchors ai-game-master's box; the-table no longer writes one
    (flatten F-1, F-6)."""
    box = tempfile.mkdtemp(prefix="the-table-agm-")
    db = os.path.join(box, "campaign.db")
    con = sqlite3.connect(db)
    for ddl in ("01_ledger.sql", "02_canon.sql", "03_entities.sql", "04_rulings.sql"):
        with open(os.path.join(_AGM, "schema", ddl)) as f:
            con.executescript(f.read())
    poc = _load(os.path.join(_AGM, "docs", "poc_vander_room.py"), "_agm_poc")
    poc.append_turn(con, 1, "session_open", "s1", {"seed": 1})
    poc.append_turn(con, 1, "turn", "one", {"turn": 0})
    poc.append_turn(con, 1, "turn", "two", {"turn": 1})
    poc.append_turn(con, 1, "session_close", "", {"summary": "done"})

    def head():
        return con.execute("SELECT hash FROM ledger ORDER BY id DESC LIMIT 1").fetchone()[0]

    def snapshot(state, note=""):
        poc.append_turn(con, 1, "turn", note, state)

    yield SimpleNamespace(db_path=db, _con=con, head=head, snapshot=snapshot)
    con.close()
    shutil.rmtree(box, ignore_errors=True)


def test_the_head_is_the_ledgers_own_head(ledger):
    got = agm_head.read(ledger.db_path)
    assert got == {"state": "read", "n": 4, "head": ledger.head(),
                   "db_sha": agm_head.db_sha(ledger.db_path)}
    r = agm_head.row(ledger.db_path)
    assert (r["n"], r["head"]) == (4, ledger.head()) and len(r["db_sha"]) == 64
    assert r["db"] == os.path.abspath(ledger.db_path)  # N4: where it was read


def test_a_missing_db_is_unreachable():
    got = agm_head.read("/nonexistent/campaign.db")
    assert got["state"] == "unreachable" and "no campaign.db" in got["why"]
    with pytest.raises(ValueError):
        agm_head.row("/nonexistent/campaign.db")


def test_an_edited_row_is_broken_and_never_anchored(ledger):
    ledger._con.execute("UPDATE ledger SET note='forged' WHERE id=2")
    ledger._con.commit()
    got = agm_head.read(ledger.db_path)
    assert got["state"] == "broken" and "id=2" in got["why"]
    with pytest.raises(ValueError):
        agm_head.row(ledger.db_path)


def test_a_rewrite_rehashed_forward_reads_with_another_head(ledger):
    """The chain verifies again; only the anchored head can tell (R9)."""
    before = ledger.head()
    con = ledger._con
    con.execute("UPDATE ledger SET note='forged' WHERE id=2")
    prev = None
    for id_, ts, sess, kind, note, state, prev_hash in con.execute(
            "SELECT id, ts, session, kind, note, state, prev_hash FROM ledger ORDER BY id").fetchall():
        p = prev if prev is not None else prev_hash
        h = _row_hash(id_, ts, sess, kind, note, state, p)
        con.execute("UPDATE ledger SET prev_hash=?, hash=? WHERE id=?", (p, h, id_))
        prev = h
    con.commit()
    got = agm_head.read(ledger.db_path)
    assert got["state"] == "read" and got["n"] == 4 and got["head"] != before


def test_cut_rows_read_fewer(ledger):
    ledger._con.execute("DELETE FROM ledger WHERE id >= 3")
    ledger._con.commit()
    got = agm_head.read(ledger.db_path)
    assert got["state"] == "read" and got["n"] == 2


def test_a_db_older_than_the_chain_is_unreachable_not_broken(tmp_path):
    db = tmp_path / "campaign.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE ledger (id INTEGER PRIMARY KEY, ts, session, kind, note, state)")
    con.commit()
    con.close()
    assert agm_head.read(str(db))["state"] == "unreachable"


def test_a_file_that_is_not_a_db_is_unreachable(tmp_path):
    db = tmp_path / "campaign.db"
    db.write_bytes(b"not sqlite at all" * 100)
    assert agm_head.read(str(db))["state"] == "unreachable"


def test_ledger_side_A7_append_then_cut_back_reads_the_anchored_head(ledger):
    """The documented limit (one-script table.check_agm_head): rows appended
    after the anchor and cut back leave (n, head) as anchored; only the
    file's hash can show it was touched."""
    before = agm_head.read(ledger.db_path)
    ledger.snapshot({"turn": 9}, note="late")
    ledger.snapshot({"turn": 10}, note="later")
    ledger._con.execute("DELETE FROM ledger WHERE id > 4")
    ledger._con.commit()
    after = agm_head.read(ledger.db_path)
    assert (after["n"], after["head"]) == (before["n"], before["head"])
