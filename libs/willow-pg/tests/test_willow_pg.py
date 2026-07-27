"""Tests for the shared willow_pg Postgres seam (box audit A5).

No live database: a fake pool/cursor is injected into willow_pg's per-DSN cache,
so the seam's behaviour (schema validation, Identifier-quoted search_path,
checkout/rollback/release) is exercised without psycopg2 talking to a server.
"""
import pytest
from psycopg2 import sql

import willow_pg as wp


# ── fakes ─────────────────────────────────────────────────────────────────────

class FakeCursor:
    def __init__(self, boom=False):
        self.executed = []
        self.closed = False
        self._boom = boom

    def execute(self, statement, *a):
        if self._boom:
            raise RuntimeError("set search_path failed")
        self.executed.append(statement)

    def close(self):
        self.closed = True


class FakeConn:
    def __init__(self, boom=False):
        self.autocommit = None
        self.rolled_back = False
        self._cur = FakeCursor(boom=boom)

    def cursor(self):
        return self._cur

    def rollback(self):
        self.rolled_back = True


class FakePool:
    def __init__(self, conn):
        self._conn = conn
        self.got = 0
        self.put = []

    def getconn(self):
        self.got += 1
        return self._conn

    def putconn(self, conn):
        self.put.append(conn)


@pytest.fixture(autouse=True)
def _clear_pools():
    wp._pools.clear()
    yield
    wp._pools.clear()


def _inject(conn, dsn=None):
    """Seed the per-DSN pool cache so get_pool never builds a real pool."""
    pool = FakePool(conn)
    wp._pools[dsn or wp.willow_dsn()] = pool
    return pool


# ── validate_schema ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("name", ["field_notes", "game_master", "a", "x9_y"])
def test_validate_schema_accepts_plain_identifiers(name):
    assert wp.validate_schema(name) == name


@pytest.mark.parametrize("name", ["", "Field_Notes", "1abc", "a-b", "a b", "a;b", "a.b", None])
def test_validate_schema_rejects_everything_else(name):
    with pytest.raises(wp.SchemaNameError):
        wp.validate_schema(name)


# ── resolve_host / willow_dsn ───────────────────────────────────────────────────

def test_resolve_host_reads_wsl_nameserver(monkeypatch):
    import io
    monkeypatch.setattr("builtins.open", lambda *a, **k: io.StringIO(
        "# comment\nnameserver 172.20.0.1\n"))
    assert wp.resolve_host() == "172.20.0.1"


def test_resolve_host_defaults_to_localhost_without_resolv_conf(monkeypatch):
    def _no_file(*a, **k):
        raise FileNotFoundError
    monkeypatch.setattr("builtins.open", _no_file)
    assert wp.resolve_host() == "localhost"


def test_willow_dsn_prefers_env(monkeypatch):
    monkeypatch.setenv("WILLOW_DB_URL", "dbname=custom user=me host=db")
    assert wp.willow_dsn() == "dbname=custom user=me host=db"


def test_willow_dsn_falls_back_to_willow(monkeypatch):
    monkeypatch.delenv("WILLOW_DB_URL", raising=False)
    monkeypatch.setattr(wp, "resolve_host", lambda: "localhost")
    assert wp.willow_dsn() == "dbname=willow user=willow host=localhost"


# ── get_connection ──────────────────────────────────────────────────────────────

def test_get_connection_scopes_with_identifier_not_interpolation():
    conn = FakeConn()
    pool = _inject(conn)
    out = wp.get_connection("field_notes")
    assert out is conn
    assert conn.autocommit is False
    assert pool.got == 1 and pool.put == []          # checked out, not released
    assert conn._cur.closed is True
    stmt = conn._cur.executed[0]
    # The statement is a psycopg2 Composed carrying an Identifier — never a str.
    assert isinstance(stmt, sql.Composed)
    idents = [x for x in stmt if isinstance(x, sql.Identifier)]
    assert idents and idents[0].strings == ("field_notes",)


def test_get_connection_validates_schema_before_touching_pool():
    pool = _inject(FakeConn())
    with pytest.raises(wp.SchemaNameError):
        wp.get_connection("public; DROP SCHEMA x")
    assert pool.got == 0                              # never reached the pool


def test_get_connection_returns_conn_to_pool_on_failure():
    conn = FakeConn(boom=True)
    pool = _inject(conn)
    with pytest.raises(RuntimeError):
        wp.get_connection("field_notes")
    assert pool.put == [conn]                         # released, not leaked


# ── release_connection ───────────────────────────────────────────────────────────

def test_release_connection_rolls_back_and_returns_to_pool():
    conn = FakeConn()
    pool = _inject(conn)
    wp.release_connection(conn)
    assert conn.rolled_back is True
    assert pool.put == [conn]


def test_release_connection_swallows_rollback_error():
    conn = FakeConn()
    conn.rollback = lambda: (_ for _ in ()).throw(RuntimeError("already closed"))
    pool = _inject(conn)
    wp.release_connection(conn)                       # must not raise
    assert pool.put == [conn]


# ── pool caching ────────────────────────────────────────────────────────────────

def test_get_pool_is_cached_per_dsn():
    p = _inject(FakeConn())
    assert wp.get_pool() is p
    assert wp.get_pool(wp.willow_dsn()) is p


# ── conn_kwargs path (unix-socket / keyword params, e.g. source-trail) ───────────

def test_conn_kwargs_pool_is_keyed_separately_from_dsn():
    kw = {"dbname": "willow_20", "user": "me", "host": None, "port": None}
    conn = FakeConn()
    pool = FakePool(conn)
    wp._pools[wp._pool_key(None, kw)] = pool
    # Same kwargs (any order) resolve to this pool; the default DSN does not.
    assert wp.get_pool(conn_kwargs=dict(reversed(list(kw.items())))) is pool
    assert wp.get_pool(conn_kwargs=kw) is pool
    assert wp._pool_key(None, kw) != wp._pool_key(None, None)


def test_get_connection_with_conn_kwargs_scopes_and_pools_by_kwargs():
    kw = {"dbname": "willow_20", "user": "me", "host": None, "port": None}
    conn = FakeConn()
    pool = FakePool(conn)
    wp._pools[wp._pool_key(None, kw)] = pool
    out = wp.get_connection("source_trail", conn_kwargs=kw)
    assert out is conn and pool.got == 1
    stmt = conn._cur.executed[0]
    idents = [x for x in stmt if isinstance(x, sql.Identifier)]
    assert idents and idents[0].strings == ("source_trail",)
    wp.release_connection(conn, conn_kwargs=kw)
    assert conn.rolled_back is True and pool.put == [conn]
