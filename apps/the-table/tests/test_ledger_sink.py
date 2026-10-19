"""the-table — test_ledger_sink.py

``ledger_sink.py`` is a TOMBSTONE (flatten F2): kept working only for the
frozen box-build records that import it. These tests keep it working for
them, and ``test_no_live_module_writes_the_retired_chain`` fails if a live
module starts writing the second chain again.

Proves LedgerSink writes rows that ai-game-master's OWN verify_ledger.py
accepts, and — the property that actually matters — that verify() can FAIL:
a verifier that can't fail is not a verifier.

Run from the app root: `python3 tests/test_ledger_sink.py`
(also collectible by `python -m pytest tests/ -q`).
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
import tempfile

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_APP_ROOT = os.path.dirname(_TESTS_DIR)  # apps/the-table
sys.path.insert(0, _APP_ROOT)

from the_table.ledger_sink import LedgerSink  # noqa: E402


def _make_box():
    return tempfile.mkdtemp(prefix="the-table-ledger-test-")


def test_open_snapshot_close_verifies_clean():
    box = _make_box()
    try:
        sink = LedgerSink(box_dir=box)
        sink.open_session("session-1", {"scene": "the door grinds open"})

        heads = []
        sink.snapshot({"round": 1, "hp": {"grask": 12}}, note="turn one")
        heads.append(sink.head())
        sink.snapshot({"round": 2, "hp": {"grask": 9}}, note="turn two")
        heads.append(sink.head())
        sink.snapshot({"round": 3, "hp": {"grask": 9, "wren": 4}}, note="turn three")
        heads.append(sink.head())

        sink.close_session({"result": "victory by restraint"})

        assert sink.verify() is True, sink._last_verify_output

        # head() advances on every snapshot — no two consecutive heads collide.
        assert len(set(heads)) == len(heads), f"chain head did not advance: {heads}"

        # head() is stable on re-read (no side effect from reading it twice).
        h1 = sink.head()
        h2 = sink.head()
        assert h1 == h2
        assert h1 not in ("", "genesis")

        sink.close()
        print("test_open_snapshot_close_verifies_clean: PASS")
    finally:
        shutil.rmtree(box, ignore_errors=True)


def test_tampered_row_is_refused():
    box = _make_box()
    try:
        sink = LedgerSink(box_dir=box)
        sink.open_session("session-2", {"scene": "the vault"})
        sink.snapshot({"round": 1}, note="turn one")
        sink.snapshot({"round": 2}, note="turn two")
        sink.snapshot({"round": 3}, note="turn three")
        sink.close_session({"result": "TBD"})

        assert sink.verify() is True, "clean chain must verify before we tamper it"

        # Tamper one ledger row's state directly, bypassing the sink entirely —
        # the same move verify_ledger.py's own --self-test performs.
        con = sqlite3.connect(sink.db_path)
        row = con.execute(
            "SELECT id FROM ledger WHERE kind='turn' ORDER BY id ASC LIMIT 1"
        ).fetchone()
        assert row is not None, "expected at least one turn row to tamper"
        target_id = row[0]
        con.execute(
            "UPDATE ledger SET state=? WHERE id=?",
            (json.dumps({"round": 1, "hp": 999999}), target_id),
        )
        con.commit()
        con.close()

        assert sink.verify() is False, "a tampered row MUST be refused by verify()"

        sink.close()
        print("test_tampered_row_is_refused: PASS")
    finally:
        shutil.rmtree(box, ignore_errors=True)


def test_no_canon_or_seal_writes():
    """The hard constraint: this sink never touches canon, never seals."""
    box = _make_box()
    try:
        sink = LedgerSink(box_dir=box)
        sink.open_session("session-3", {"scene": "check"})
        sink.snapshot({"a": 1})
        sink.close_session({"result": "n/a"})

        con = sqlite3.connect(sink.db_path)
        canon_rows = con.execute("SELECT COUNT(*) FROM canon").fetchone()[0]
        con.close()
        assert canon_rows == 0, "LedgerSink must never write to the canon table"

        assert sink.verify() is True, sink._last_verify_output

        sink.close()
        print("test_no_canon_or_seal_writes: PASS")
    finally:
        shutil.rmtree(box, ignore_errors=True)


def main() -> int:
    test_open_snapshot_close_verifies_clean()
    test_tampered_row_is_refused()
    test_no_canon_or_seal_writes()
    print("\nall tests PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def test_no_live_module_writes_the_retired_chain():
    """Forbidden act: a live the-table module or aetheris5e script importing
    the retired ledger sink (one chain, flatten F-1). The tombstone itself and
    this file are the only places it may be named in code."""
    import re as _re

    app = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pat = _re.compile(r"^\s*(from\s+\S*ledger_sink\s+import|import\s+\S*ledger_sink)", _re.M)
    hits = []
    for sub in ("the_table", "aetheris5e", "tests"):
        for name in sorted(os.listdir(os.path.join(app, sub))):
            if not name.endswith(".py") or name in ("ledger_sink.py", "test_ledger_sink.py"):
                continue
            with open(os.path.join(app, sub, name), encoding="utf-8") as f:
                if pat.search(f.read()):
                    hits.append(f"{sub}/{name}")
    assert hits == [], f"live modules import the retired ledger sink: {hits}"

