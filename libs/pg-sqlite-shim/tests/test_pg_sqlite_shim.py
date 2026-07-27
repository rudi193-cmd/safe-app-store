"""Tests for the shared pg_sqlite_shim SQLite->Postgres seam (box audit A5).

No live database: fake psycopg2 cursor/conn/pool objects are handed to
PgCursor/PgConn, so the shim's behaviour (SQL translation, RETURNING-aware and
SAVEPOINT-guarded lastrowid, row_factory, executemany, context-manager exit) is
exercised without psycopg2 ever talking to a server.
"""
import sqlite3

import psycopg2.extras
import pytest

import pg_sqlite_shim as shim


# ── fakes ─────────────────────────────────────────────────────────────────────

class FakeCursor:
    """Records translated statements and answers fetches deterministically.

    ``lastval`` is the value ``SELECT lastval()`` yields (None => no row, i.e. a
    TEXT-PK table with no sequence). ``lastval_boom`` makes that probe raise, to
    exercise the SAVEPOINT rollback branch. ``returning`` is what ``fetchone``
    returns for a normal (RETURNING/SELECT) statement.
    """

    def __init__(self, *, lastval=None, lastval_boom=False, returning=None, rows=None):
        self.executed = []
        self.description = None
        self.rowcount = -1
        self.closed = False
        self._lastval = lastval
        self._lastval_boom = lastval_boom
        self._returning = returning
        self._rows = rows or []
        self._mode = None

    def execute(self, sql, params=None):
        self.executed.append(sql)
        low = sql.lower()
        if "lastval()" in low:
            if self._lastval_boom:
                raise RuntimeError("lastval failed: no sequence used")
            self._mode = "lastval"
        elif sql.startswith(("SAVEPOINT", "RELEASE", "ROLLBACK")):
            self._mode = "savepoint"
        else:
            self._mode = "normal"
        self.description = [("col",)] if low.lstrip().startswith("select") else None
        self.rowcount = 1

    def fetchone(self):
        if self._mode == "lastval":
            return (self._lastval,) if self._lastval is not None else None
        return self._returning

    def fetchall(self):
        return list(self._rows)

    def fetchmany(self, n):
        return list(self._rows[:n])

    def close(self):
        self.closed = True

    def __iter__(self):
        return iter(self._rows)


class FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor
        self.committed = False
        self.rolled_back = False
        self.cursor_factory = "UNSET"

    def cursor(self, cursor_factory=None):
        self.cursor_factory = cursor_factory
        return self._cursor

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


class FakePool:
    def __init__(self):
        self.put = []

    def putconn(self, conn):
        self.put.append(conn)


# ── sqlite_to_pg: translation ───────────────────────────────────────────────────

@pytest.mark.parametrize("sql", [
    "PRAGMA foreign_keys=ON",
    "  pragma table_info(cases)",
    "PRAGMA journal_mode=WAL;",
])
def test_pragma_becomes_select_1(sql):
    assert shim.sqlite_to_pg(sql) == "SELECT 1"


def test_insert_or_ignore_becomes_on_conflict_do_nothing():
    out = shim.sqlite_to_pg("INSERT OR IGNORE INTO t (a) VALUES (?)")
    assert out == "INSERT INTO t (a) VALUES (%s) ON CONFLICT DO NOTHING"


def test_insert_or_replace_uses_app_conflict_target():
    targets = {"oral_clubs": "(name) DO UPDATE SET city=EXCLUDED.city"}
    out = shim.sqlite_to_pg(
        "INSERT OR REPLACE INTO oral_clubs (name, city) VALUES (?, ?)", targets)
    assert out == (
        "INSERT INTO oral_clubs (name, city) VALUES (%s, %s) "
        "ON CONFLICT (name) DO UPDATE SET city=EXCLUDED.city")


def test_insert_or_replace_unknown_table_defaults_to_do_nothing():
    out = shim.sqlite_to_pg("INSERT OR REPLACE INTO widgets (a) VALUES (?)", {})
    assert out == "INSERT INTO widgets (a) VALUES (%s) ON CONFLICT DO NOTHING"


def test_insert_or_replace_none_targets_behaves_like_empty():
    out = shim.sqlite_to_pg("INSERT OR REPLACE INTO widgets (a) VALUES (?)")
    assert out.endswith("ON CONFLICT DO NOTHING")


def test_trailing_semicolon_stripped_before_on_conflict():
    out = shim.sqlite_to_pg("INSERT OR IGNORE INTO t (a) VALUES (?);")
    assert out == "INSERT INTO t (a) VALUES (%s) ON CONFLICT DO NOTHING"


def test_question_marks_translate_and_percent_escaped_only_when_qmarks_present():
    # ? present -> literal % must be escaped to %% so psycopg2 doesn't read it
    # as a placeholder, and each ? becomes %s.
    out = shim.sqlite_to_pg("SELECT * FROM t WHERE name LIKE '%x%' AND id = ?")
    assert out == "SELECT * FROM t WHERE name LIKE '%%x%%' AND id = %s"


def test_native_percent_s_left_untouched_when_no_qmarks():
    # Already Postgres-native (%s, and a LIKE %): must not be double-escaped.
    sql = "SELECT * FROM t WHERE name LIKE '%foo%' AND id = %s"
    assert shim.sqlite_to_pg(sql) == sql


def test_returning_passthrough_with_placeholders():
    out = shim.sqlite_to_pg("INSERT INTO t (a) VALUES (?) RETURNING id")
    assert out == "INSERT INTO t (a) VALUES (%s) RETURNING id"


# ── PgCursor: execute / lastrowid ────────────────────────────────────────────────

def test_execute_translates_before_running_and_returns_self():
    raw = FakeCursor()
    cur = shim.PgCursor(raw)
    out = cur.execute("PRAGMA foreign_keys=ON")
    assert out is cur
    assert raw.executed == ["SELECT 1"]


def test_execute_uses_cursor_conflict_targets():
    raw = FakeCursor()
    cur = shim.PgCursor(raw, {"t": "(a) DO UPDATE SET a=EXCLUDED.a"})
    cur.execute("INSERT OR REPLACE INTO t (a) VALUES (?)")
    assert raw.executed[0] == (
        "INSERT INTO t (a) VALUES (%s) ON CONFLICT (a) DO UPDATE SET a=EXCLUDED.a")


def test_insert_with_returning_skips_lastval_and_leaves_result_for_caller():
    raw = FakeCursor(returning=(99,))
    cur = shim.PgCursor(raw)
    cur.execute("INSERT INTO t (a) VALUES (?) RETURNING id", (1,))
    assert cur.lastrowid is None                     # RETURNING result is the caller's
    assert not any("lastval" in s for s in raw.executed)
    assert not any(s.startswith("SAVEPOINT") for s in raw.executed)
    assert cur.fetchone() == (99,)


def test_insert_without_returning_uses_savepoint_guarded_lastval():
    raw = FakeCursor(lastval=42)
    cur = shim.PgCursor(raw)
    cur.execute("INSERT INTO t (a) VALUES (?)", (1,))
    assert cur.lastrowid == 42
    assert raw.executed[0].startswith("INSERT INTO t")
    assert "SAVEPOINT _lastval_check" in raw.executed
    assert any("lastval()" in s for s in raw.executed)
    assert "RELEASE SAVEPOINT _lastval_check" in raw.executed
    assert "ROLLBACK TO SAVEPOINT _lastval_check" not in raw.executed


def test_insert_without_sequence_yields_none_lastrowid():
    raw = FakeCursor(lastval=None)                   # WHERE EXISTS -> no row
    cur = shim.PgCursor(raw)
    cur.execute("INSERT INTO t (a) VALUES (?)", (1,))
    assert cur.lastrowid is None


def test_failed_lastval_rolls_back_to_savepoint_and_does_not_poison_txn():
    raw = FakeCursor(lastval_boom=True)
    cur = shim.PgCursor(raw)
    cur.execute("INSERT INTO t (a) VALUES (?)", (1,))
    assert cur.lastrowid is None
    assert "ROLLBACK TO SAVEPOINT _lastval_check" in raw.executed


def test_non_insert_statement_has_none_lastrowid_and_no_savepoint():
    raw = FakeCursor(rows=[(1,)])
    cur = shim.PgCursor(raw)
    cur.execute("SELECT * FROM t WHERE id = ?", (1,))
    assert cur.lastrowid is None
    assert not any(s.startswith("SAVEPOINT") for s in raw.executed)


def test_executemany_translates_and_delegates_to_execute_batch(monkeypatch):
    calls = {}

    def fake_execute_batch(cur, sql, seq):
        calls["cur"] = cur
        calls["sql"] = sql
        calls["seq"] = seq

    monkeypatch.setattr(psycopg2.extras, "execute_batch", fake_execute_batch)
    raw = FakeCursor()
    cur = shim.PgCursor(raw)
    cur.executemany("INSERT OR IGNORE INTO t (a) VALUES (?)", [(1,), (2,)])
    assert calls["cur"] is raw
    assert calls["sql"] == "INSERT INTO t (a) VALUES (%s) ON CONFLICT DO NOTHING"
    assert calls["seq"] == [(1,), (2,)]


def test_getattr_falls_through_to_wrapped_cursor():
    raw = FakeCursor()
    raw.mogrify = lambda *a: b"x"
    cur = shim.PgCursor(raw)
    assert cur.mogrify() == b"x"


# ── PgConn ───────────────────────────────────────────────────────────────────────

def test_cursor_default_wraps_plain_cursor_and_carries_targets():
    raw = FakeCursor()
    conn = FakeConn(raw)
    targets = {"t": "(a) DO NOTHING"}
    pg = shim.PgConn(FakePool(), conn, conflict_targets=targets)
    cur = pg.cursor()
    assert isinstance(cur, shim.PgCursor)
    assert conn.cursor_factory is None
    assert cur._conflict_targets is targets


def test_cursor_with_row_factory_row_uses_realdictcursor():
    raw = FakeCursor()
    conn = FakeConn(raw)
    pg = shim.PgConn(FakePool(), conn)
    pg.row_factory = sqlite3.Row
    pg.cursor()
    assert conn.cursor_factory is psycopg2.extras.RealDictCursor


def test_execute_convenience_returns_cursor_and_runs():
    raw = FakeCursor(lastval=5)
    conn = FakeConn(raw)
    pg = shim.PgConn(FakePool(), conn)
    cur = pg.execute("INSERT INTO t (a) VALUES (?)", (1,))
    assert isinstance(cur, shim.PgCursor)
    assert cur.lastrowid == 5


def test_executescript_passes_through_and_closes_raw_cursor():
    raw = FakeCursor()
    conn = FakeConn(raw)
    pg = shim.PgConn(FakePool(), conn)
    pg.executescript("CREATE TABLE t (a int); CREATE TABLE u (b int);")
    assert raw.executed == ["CREATE TABLE t (a int); CREATE TABLE u (b int);"]
    assert raw.closed is True


def test_row_factory_property_roundtrips():
    pg = shim.PgConn(FakePool(), FakeConn(FakeCursor()))
    assert pg.row_factory is None
    pg.row_factory = sqlite3.Row
    assert pg.row_factory is sqlite3.Row


def test_getattr_falls_through_to_wrapped_conn():
    conn = FakeConn(FakeCursor())
    conn.server_version = 140000
    pg = shim.PgConn(FakePool(), conn)
    assert pg.server_version == 140000


def test_close_rolls_back_and_returns_to_pool():
    conn = FakeConn(FakeCursor())
    pool = FakePool()
    pg = shim.PgConn(pool, conn)
    pg.close()
    assert conn.rolled_back is True
    assert pool.put == [conn]


def test_default_exit_always_rolls_back_even_on_clean_exit():
    # commit_on_exit defaults False (nasa-archive's contract): __exit__ rolls
    # back; explicit commit() is required to keep writes.
    conn = FakeConn(FakeCursor())
    pool = FakePool()
    with shim.PgConn(pool, conn):
        pass
    assert conn.committed is False
    assert conn.rolled_back is True
    assert pool.put == [conn]


def test_commit_on_exit_true_commits_on_clean_exit():
    conn = FakeConn(FakeCursor())
    pool = FakePool()
    with shim.PgConn(pool, conn, commit_on_exit=True):
        pass
    assert conn.committed is True
    assert conn.rolled_back is False
    assert pool.put == [conn]


def test_commit_on_exit_true_rolls_back_on_exception():
    conn = FakeConn(FakeCursor())
    pool = FakePool()
    with pytest.raises(ValueError):
        with shim.PgConn(pool, conn, commit_on_exit=True):
            raise ValueError("boom")
    assert conn.committed is False
    assert conn.rolled_back is True
    assert pool.put == [conn]


def test_conflict_targets_propagate_through_conn_execute():
    raw = FakeCursor()
    conn = FakeConn(raw)
    pg = shim.PgConn(FakePool(), conn,
                     conflict_targets={"t": "(a) DO UPDATE SET a=EXCLUDED.a"})
    pg.execute("INSERT OR REPLACE INTO t (a) VALUES (?)", (1,))
    assert raw.executed[0].endswith("ON CONFLICT (a) DO UPDATE SET a=EXCLUDED.a")
