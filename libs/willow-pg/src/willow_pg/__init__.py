"""willow_pg — the one shared Postgres seam for hosted apps.

Every PostgreSQL-backed app hand-rolled the same connection boilerplate: a
module-level pool, a WSL ``/etc/resolv.conf`` host fallback, a ``dbname=willow``
DSN, and a ``get_connection`` that scopes the session to the app's schema with
``SET search_path``. That last step is the security-relevant one — it is what
keeps one app's queries inside its own schema — and it had drifted: most apps
built the statement with an f-string, one used ``sql.Identifier`` (box audit
A5, and the format-string-SQL finding). This module is the single home for that
seam:

  * ``validate_schema`` — a schema name must be a plain lowercase identifier
    (``[a-z_][a-z0-9_]*``); anything else raises before it can reach SQL.
  * ``get_connection(schema)`` — a pooled connection with ``search_path`` set to
    ``<schema>, public`` via ``sql.Identifier`` — never string interpolation.
  * ``release_connection(conn)`` — roll back and return the connection to its
    pool.

psycopg2 is imported lazily (inside the functions that need it), so importing
``willow_pg`` never requires the driver — apps can import their db module in a
stdlib-only context, exactly as the hand-rolled versions did.
"""
from __future__ import annotations

import os
import re
import threading
from typing import Optional

__all__ = [
    "SchemaNameError", "validate_schema", "resolve_host", "willow_dsn",
    "get_pool", "get_connection", "release_connection",
]

_IDENT = re.compile(r"[a-z_][a-z0-9_]*")

# Pools are cached per DSN. Each hosted app is its own process, so this is a
# single pool per process for the default DSN — the same lifetime the module
# globals had, minus the copy-per-app.
_pools: dict = {}
_lock = threading.Lock()


class SchemaNameError(ValueError):
    """The schema name is not a plain lowercase identifier (ST-SQL-01)."""


def validate_schema(name: str) -> str:
    """Return ``name`` if it is a plain lowercase SQL identifier, else raise.

    Schema names can't be passed as query parameters; validating here means an
    unexpected value is rejected loudly at the seam rather than reaching SQL."""
    if not name or not _IDENT.fullmatch(name):
        raise SchemaNameError(f"Invalid schema name: {name!r}")
    return name


def resolve_host() -> str:
    """localhost, falling back to the WSL ``resolv.conf`` nameserver when set."""
    host = "localhost"
    try:
        with open("/etc/resolv.conf") as f:
            for line in f:
                if line.strip().startswith("nameserver"):
                    host = line.strip().split()[1]
                    break
    except FileNotFoundError:
        pass
    return host


def willow_dsn() -> str:
    """The default Willow DSN: ``WILLOW_DB_URL`` if set, else a localhost/WSL
    ``dbname=willow`` connection."""
    dsn = os.getenv("WILLOW_DB_URL", "")
    return dsn or f"dbname=willow user=willow host={resolve_host()}"


def _pool_key(dsn: Optional[str], conn_kwargs: Optional[dict]):
    """A stable, hashable cache key: the sorted kwargs when given (an app that
    connects with keyword params, e.g. a unix socket), else the DSN string."""
    if conn_kwargs is not None:
        return ("kw",) + tuple(sorted(conn_kwargs.items()))
    return dsn or willow_dsn()


def get_pool(dsn: Optional[str] = None, *, conn_kwargs: Optional[dict] = None,
             minconn: int = 1, maxconn: int = 10):
    """Return the pool for this connection spec, creating it once and caching it.

    Pass ``dsn`` (default: :func:`willow_dsn`) for a DSN string, or
    ``conn_kwargs`` for keyword connection params (``dbname=``, ``user=``,
    ``host=None`` for a unix socket, …). psycopg2 is imported here, so a module
    that only imports ``willow_pg`` needs no driver installed."""
    key = _pool_key(dsn, conn_kwargs)
    pool = _pools.get(key)
    if pool is not None:
        return pool
    with _lock:
        if key not in _pools:
            import psycopg2.pool
            if conn_kwargs is not None:
                _pools[key] = psycopg2.pool.ThreadedConnectionPool(
                    minconn, maxconn, **conn_kwargs)
            else:
                _pools[key] = psycopg2.pool.ThreadedConnectionPool(
                    minconn, maxconn, dsn=(dsn or willow_dsn()))
        return _pools[key]


def get_connection(schema: str, dsn: Optional[str] = None, *,
                   conn_kwargs: Optional[dict] = None):
    """Return a pooled connection with ``search_path = <schema>, public``.

    The schema name is validated and placed with ``sql.Identifier`` — never
    string-interpolated. On any failure setting the search_path the connection
    is returned to the pool before re-raising, so a failed checkout never leaks.
    See :func:`get_pool` for ``dsn`` vs ``conn_kwargs``."""
    validate_schema(schema)
    from psycopg2 import sql
    pool = get_pool(dsn, conn_kwargs=conn_kwargs)
    conn = pool.getconn()
    try:
        conn.autocommit = False
        cur = conn.cursor()
        cur.execute(sql.SQL("SET search_path = {}, public").format(sql.Identifier(schema)))
        cur.close()
        return conn
    except Exception:
        pool.putconn(conn)
        raise


def release_connection(conn, dsn: Optional[str] = None, *,
                       conn_kwargs: Optional[dict] = None) -> None:
    """Roll back and return ``conn`` to its pool. Swallows a rollback error so
    release is always safe to call in a ``finally``. Pass the same ``dsn`` /
    ``conn_kwargs`` the connection was checked out with."""
    try:
        conn.rollback()
    except Exception:
        pass
    get_pool(dsn, conn_kwargs=conn_kwargs).putconn(conn)
