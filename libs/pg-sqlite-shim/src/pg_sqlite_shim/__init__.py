"""pg_sqlite_shim — the one SQLite->Postgres compatibility shim for hosted apps.

Several apps grew Postgres-backed while their query code was still written in
SQLite dialect. Each hand-rolled the same shim: a ``_sqlite_to_pg`` translator
(``PRAGMA`` -> ``SELECT 1``; ``INSERT OR IGNORE/REPLACE`` -> ``ON CONFLICT``;
``?`` -> ``%s``) plus ``_PgCursor`` / ``_PgConn`` wrappers giving a psycopg2
connection a sqlite3-compatible surface (``lastrowid``, ``row_factory``,
``executescript``). The copies had **drifted** (box audit A5): nasa-archive's
was the hardened superset — a SAVEPOINT-guarded ``lastval()`` and a
``RETURNING``-aware ``lastrowid`` — while law-gazelle's was a simpler earlier
form. This module is the single, hardened home for that seam.

  * ``sqlite_to_pg(sql, conflict_targets=...)`` — the translator. Conflict
    targets are **app-specific data** (which column an upsert keys on, and what
    to SET); each app keeps its own mapping and passes it in.
  * ``PgCursor`` — a psycopg2 cursor behind sqlite3's interface. ``execute``
    translates first; ``lastrowid`` prefers a ``RETURNING`` result, else a
    SAVEPOINT-guarded ``lastval()`` (so a TEXT-PK insert with no sequence does
    not poison the transaction); ``executemany`` uses ``execute_batch``.
  * ``PgConn`` — a pooled psycopg2 connection behind sqlite3's interface:
    ``cursor()`` honours a ``sqlite3.Row`` ``row_factory`` (via
    ``RealDictCursor``), ``execute`` / ``executescript`` convenience, and a
    context manager whose exit behaviour each app selects (``commit_on_exit``).

psycopg2 is imported lazily (inside the methods that need it), so importing
``pg_sqlite_shim`` never requires the driver — an app can import its db module
in a stdlib-only context (e.g. a compile sweep), exactly as the hand-rolled
versions did.
"""
from __future__ import annotations

import re
from typing import Mapping, Optional

__all__ = ["sqlite_to_pg", "PgCursor", "PgConn"]


def sqlite_to_pg(sql: str, conflict_targets: Optional[Mapping[str, str]] = None) -> str:
    """Translate a SQLite SQL statement to its PostgreSQL equivalent.

    * ``PRAGMA ...`` -> ``SELECT 1`` (SQLite pragmas have no Postgres meaning).
    * ``INSERT OR IGNORE ...`` -> ``INSERT ... ON CONFLICT DO NOTHING``.
    * ``INSERT OR REPLACE INTO <t> ...`` -> ``INSERT ... ON CONFLICT <target>``
      where ``<target>`` comes from ``conflict_targets[<t>]`` (an app-specific
      ``"(col) DO UPDATE SET ..."`` clause), defaulting to ``DO NOTHING`` when
      the table is unknown.
    * ``?`` placeholders -> ``%s`` — **only** when the statement actually uses
      ``?``. A statement already written with ``%s`` (Postgres-native) is left
      untouched; escaping its ``%`` would turn ``%s`` into ``%%s`` and break
      psycopg2. When ``?`` is present, literal ``%`` is first escaped to ``%%``.

    ``conflict_targets`` is app-specific data (see the module docstring); pass
    the app's mapping. ``None`` behaves like an empty mapping.
    """
    if conflict_targets is None:
        conflict_targets = {}
    s = sql.strip()
    if re.match(r"\s*PRAGMA\b", s, re.IGNORECASE):
        return "SELECT 1"
    if re.search(r"\bINSERT\s+OR\s+IGNORE\b", s, re.IGNORECASE):
        s = re.sub(r"\bINSERT\s+OR\s+IGNORE\b", "INSERT", s, flags=re.IGNORECASE)
        s = s.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
    elif re.search(r"\bINSERT\s+OR\s+REPLACE\b", s, re.IGNORECASE):
        s = re.sub(r"\bINSERT\s+OR\s+REPLACE\b", "INSERT", s, flags=re.IGNORECASE)
        m = re.search(r"\bINSERT\s+INTO\s+[\"']?(\w+)", s, re.IGNORECASE)
        table = m.group(1).lower() if m else ""
        conflict = conflict_targets.get(table, "DO NOTHING")
        s = s.rstrip().rstrip(";") + f" ON CONFLICT {conflict}"
    # Only translate ? -> %s if the query uses SQLite-style placeholders.
    # If it already uses %s (Postgres-native), leave it alone — escaping % would
    # turn %s into %%s and break psycopg2.
    if "?" in s:
        s = s.replace("%", "%%")
        s = s.replace("?", "%s")
    return s


class PgCursor:
    """A psycopg2 cursor wrapped to present sqlite3's cursor interface.

    ``execute`` runs the statement through :func:`sqlite_to_pg` (with the
    ``conflict_targets`` this cursor was built with) before executing, and
    maintains a sqlite3-style ``lastrowid``. Unknown attributes fall through to
    the wrapped cursor.
    """

    def __init__(self, cur, conflict_targets: Optional[Mapping[str, str]] = None):
        self._cur = cur
        self._conflict_targets = conflict_targets or {}
        self.description = cur.description
        self.rowcount = cur.rowcount
        self.lastrowid = None

    def __getattr__(self, name):
        return getattr(self._cur, name)

    def execute(self, sql, params=None):
        pg_sql = sqlite_to_pg(sql, self._conflict_targets)
        # If the INSERT carries RETURNING, that result set IS the returned
        # row(s) — don't consume it for lastrowid; let the caller fetch it.
        has_returning = bool(re.search(r"\bRETURNING\b", pg_sql, re.IGNORECASE))
        self._cur.execute(pg_sql, params)
        self.description = self._cur.description
        self.rowcount = self._cur.rowcount
        if has_returning:
            self.lastrowid = None
        elif re.match(r"\s*INSERT\b", pg_sql, re.IGNORECASE):
            # No RETURNING — try lastval() for SERIAL/IDENTITY columns. lastval()
            # errors if no sequence was touched (a TEXT-PK table), so guard it
            # with a SAVEPOINT: a failed probe rolls back to the savepoint
            # instead of poisoning the whole transaction.
            try:
                self._cur.execute("SAVEPOINT _lastval_check")
                self._cur.execute(
                    "SELECT lastval() WHERE EXISTS ("
                    "  SELECT 1 FROM pg_sequences LIMIT 1"
                    ")"
                )
                row = self._cur.fetchone()
                self.lastrowid = row[0] if row else None
                self._cur.execute("RELEASE SAVEPOINT _lastval_check")
            except Exception:
                try:
                    self._cur.execute("ROLLBACK TO SAVEPOINT _lastval_check")
                    self._cur.execute("RELEASE SAVEPOINT _lastval_check")
                except Exception:
                    pass
                self.lastrowid = None
        else:
            self.lastrowid = None
        return self

    def executemany(self, sql, seq):
        import psycopg2.extras
        pg_sql = sqlite_to_pg(sql, self._conflict_targets)
        psycopg2.extras.execute_batch(self._cur, pg_sql, seq)

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    def fetchmany(self, n):
        return self._cur.fetchmany(n)

    def __iter__(self):
        return iter(self._cur)


class PgConn:
    """A pooled psycopg2 connection wrapped to present sqlite3's interface.

    ``cursor()`` returns a :class:`PgCursor` carrying this connection's
    ``conflict_targets``; when ``row_factory`` is set to ``sqlite3.Row`` the
    underlying cursor becomes a psycopg2 ``RealDictCursor`` so rows are
    dict-like. Unknown attributes fall through to the wrapped connection.

    ``commit_on_exit`` selects the context-manager exit contract:

    * ``False`` (default) — ``__exit__`` always rolls back; callers that want
      their writes kept must ``commit()`` explicitly. (nasa-archive's contract.)
    * ``True`` — ``__exit__`` commits on a clean exit and rolls back on an
      exception. (law-gazelle's contract.)

    ``close()`` always rolls back any open transaction before returning the
    connection to the pool, so a checked-in connection never carries state.
    """

    def __init__(self, pool, conn, conflict_targets: Optional[Mapping[str, str]] = None,
                 commit_on_exit: bool = False):
        self._pool = pool
        self._conn = conn
        self._conflict_targets = conflict_targets or {}
        self._commit_on_exit = commit_on_exit
        self._row_factory = None

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def cursor(self):
        import sqlite3 as _sqlite3
        if self._row_factory is _sqlite3.Row:
            import psycopg2.extras
            return PgCursor(
                self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor),
                self._conflict_targets,
            )
        return PgCursor(self._conn.cursor(), self._conflict_targets)

    def execute(self, sql, params=None):
        cur = self.cursor()
        cur.execute(sql, params)
        return cur

    def executescript(self, sql: str):
        """Run a multi-statement SQL script (sqlite3.Connection.executescript
        compat). Passed straight through; SQLite-only DDL should already be
        Postgres-compatible."""
        cur = self._conn.cursor()
        cur.execute(sql)
        cur.close()

    @property
    def row_factory(self):
        return self._row_factory

    @row_factory.setter
    def row_factory(self, value):
        self._row_factory = value

    def close(self):
        try:
            self._conn.rollback()
        except Exception:
            pass
        self._pool.putconn(self._conn)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, *_):
        try:
            if self._commit_on_exit and exc_type is None:
                self._conn.commit()
            else:
                self._conn.rollback()
        except Exception:
            pass
        self._pool.putconn(self._conn)
