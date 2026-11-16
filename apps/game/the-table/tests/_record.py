"""_record.py -- the one-script record as these tests' sink (flatten F2).

The integration tests used to record each game into an ai-game-master
``campaign.db`` through ``LedgerSink`` and ask ``verify_ledger.py``. The
record is now the one chain (F-1): ``RecordedSink`` plays a game into a
one-script box found beside the-table (``the_table/host.py``) through the
``OneScriptSink``, and ``verify()`` is the one-script's own ``verify_chain``
and ``verify_anchor``. It keeps the surface those tests read (``verify``,
``_last_verify_output``, ``head``, ``close``), so each test reads as before.

With no one-script beside, the test is skipped, and says why.
"""
from __future__ import annotations

import unittest

from the_table import host


class RecordedSink:
    """``OneScriptSink`` on a ``host.Box`` under ``box_dir``."""

    def __init__(self, box_dir: str, *, game=None, game_name: str = "test") -> None:
        got = host.reach()
        if got["state"] != "reachable":
            raise unittest.SkipTest(f"the one-script is not beside the-table: {got['why']}")
        self.box = host.Box(box_dir)
        self._sink = self.box.sink(game=game, game_name=game_name)
        self._last_verify_output = ""

    @property
    def rows(self) -> list:
        return self._sink.rows

    def open_session(self, session_id: str, meta: dict) -> None:
        self._sink.open_session(session_id, meta)

    def snapshot(self, state: dict, note: str = "") -> None:
        self._sink.snapshot(state, note=note)

    def close_session(self, result: dict) -> None:
        self._sink.close_session(result)

    def verify(self) -> bool:
        breaks = self.box.verify()
        self._last_verify_output = "\n".join(breaks)
        return not breaks

    def head(self):
        return self.box.head()

    def close(self) -> None:
        self.box.close()
