"""the-table -- test_agm_head.py (J9, box-build SPEC R9).

``agm_head.read`` recomputes campaign.db's head with ai-game-master's own
``verify_ledger.py``: read / broken / unreachable, never collapsed. A broken
or unreachable ledger is never anchored.
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import sys
import tempfile

import pytest

_APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _APP_ROOT)

from the_table import agm_head
from the_table.ledger_sink import LedgerSink, _row_hash


@pytest.fixture
def ledger():
    box = tempfile.mkdtemp(prefix="the-table-agm-")
    sink = LedgerSink(box_dir=box)
    sink.open_session("s1", {"seed": 1})
    sink.snapshot({"turn": 0}, note="one")
    sink.snapshot({"turn": 1}, note="two")
    sink.close_session({"summary": "done"})
    yield sink
    sink.close()
    shutil.rmtree(box, ignore_errors=True)


def test_the_head_is_the_ledger_sinks_head(ledger):
    got = agm_head.read(ledger.db_path)
    assert got == {"state": "read", "n": 4, "head": ledger.head()}
    r = agm_head.row(ledger.db_path)
    assert (r["n"], r["head"]) == (4, ledger.head()) and len(r["db_sha"]) == 64


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
