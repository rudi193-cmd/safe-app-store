"""Drift-guard: no app builds a schema DDL/DML statement by string interpolation.

Box-audit finding: across the Postgres-backed apps, ``SET search_path`` and
``CREATE SCHEMA IF NOT EXISTS`` were assembled with f-strings —
``cur.execute(f"SET search_path = {SCHEMA}, public")``. Every offending site
interpolated a *hardcoded, regex-validated* schema constant, so none was a live
injection, but format-string SQL construction is the exact pattern a scanner
flags and the exact habit that puts a user-controlled value one refactor away
from the query text. utety-chat already did it the safe way — psycopg2's
``sql.SQL(...).format(sql.Identifier(SCHEMA))`` — and the rest of the fleet was
converged onto that form.

This test fails if any live (non-archived) app file reintroduces an
interpolated ``SET search_path`` or ``CREATE SCHEMA`` (f-string, ``%``, ``+``,
or ``str.format``), so the pattern can't creep back the way it spread.
Identifier quoting via ``psycopg2.sql`` is the one sanctioned way to place a
schema name into a statement.
"""
import re
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent

# A statement text that contains SET search_path or CREATE SCHEMA and is being
# built by interpolation rather than passed as a literal to sql.SQL(...).
# Match the unsafe carriers: f-strings, %-formatting, string concatenation, and
# .format() applied to a plain str template (not sql.SQL).
_STMT = r'(SET\s+search_path|CREATE\s+SCHEMA)'
_PATTERNS = [
    # f"... SET search_path ..."  /  f"... CREATE SCHEMA ..."
    re.compile(r'f["\'][^"\']*' + _STMT, re.IGNORECASE),
    # "... SET search_path ..." % ...   (printf-style)
    re.compile(r'["\'][^"\']*' + _STMT + r'[^"\']*["\']\s*%', re.IGNORECASE),
    # "... SET search_path ..." + var   (concatenation)
    re.compile(r'["\'][^"\']*' + _STMT + r'[^"\']*["\']\s*\+', re.IGNORECASE),
    # "... SET search_path ...".format(  (str.format, not sql.SQL(...).format)
    re.compile(r'["\'][^"\']*' + _STMT + r'[^"\']*["\']\s*\.format\(', re.IGNORECASE),
]

_SKIP_PARTS = {"_archived", "__pycache__", ".git", "node_modules", ".venv", "venv"}


def _live_py_files():
    for p in (_REPO / "apps").rglob("*.py"):
        if _SKIP_PARTS & set(p.parts):
            continue
        yield p


def test_no_interpolated_schema_sql():
    offenders = []
    for p in _live_py_files():
        text = p.read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(text.splitlines(), 1):
            if not re.search(_STMT, line, re.IGNORECASE):
                continue
            if any(pat.search(line) for pat in _PATTERNS):
                offenders.append(f"{p.relative_to(_REPO)}:{i}  {line.strip()}")
    assert not offenders, (
        "schema DDL/DML built by string interpolation (box audit) — place the "
        "schema name with psycopg2's sql.SQL(...).format(sql.Identifier(...)) "
        "instead:\n  " + "\n  ".join(sorted(offenders)))
