"""The compiler's precedence rule, tested directly rather than through the store.

    (allow1 OR allow2) AND NOT (deny1 OR deny2)

Denies negate the *union* of the allows. The failure mode this guards against is
subtle and silent: drop the parentheses around the joined denies and only the
first deny term binds, so the second one quietly stops applying and every row it
was meant to withhold becomes visible. Nothing raises. The tests below are the
only thing that notices.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from marching_arts.rules import (  # noqa: E402
    DENY_ALL, Effect, Rule, compile_rules, explain,
)


def _rows(predicate: str, params: dict, table: str = "t") -> list[int]:
    """Evaluate a compiled predicate against a scratch table of integers."""
    conn = sqlite3.connect(":memory:")
    conn.execute(f"CREATE TABLE {table}(n INTEGER)")
    conn.executemany(f"INSERT INTO {table} VALUES (?)", [(i,) for i in range(10)])
    return [r[0] for r in conn.execute(
        f"SELECT n FROM {table} WHERE {predicate} ORDER BY n", params)]


def test_no_allows_denies_everything():
    sql, params = compile_rules([])
    assert sql == DENY_ALL
    assert _rows(sql, params) == []


def test_denies_alone_still_deny_everything():
    """A policy of nothing but prohibitions grants nothing. Fail closed."""
    sql, params = compile_rules([Rule(Effect.DENY, "n = 3")])
    assert sql == DENY_ALL
    assert _rows(sql, params) == []


def test_allows_are_unioned():
    sql, params = compile_rules([
        Rule(Effect.ALLOW, "n < 2"),
        Rule(Effect.ALLOW, "n > 7"),
    ])
    assert _rows(sql, params) == [0, 1, 8, 9]


def test_deny_negates_the_union_not_the_first_term():
    """The regression test for the missing-parentheses bug.

    With correct precedence, n=1 is denied even though it was permitted by the
    *first* allow, and n=8 is denied even though it was permitted by the second.
    """
    sql, params = compile_rules([
        Rule(Effect.ALLOW, "n < 2"),
        Rule(Effect.ALLOW, "n > 7"),
        Rule(Effect.DENY, "n = 1"),
        Rule(Effect.DENY, "n = 8"),
    ])
    assert _rows(sql, params) == [0, 9]


def test_a_later_allow_cannot_reopen_a_denied_row():
    """Order does not matter; effect does. This is why they are two lists."""
    sql, params = compile_rules([
        Rule(Effect.DENY, "n = 5"),
        Rule(Effect.ALLOW, "n >= 0"),
        Rule(Effect.ALLOW, "n = 5"),
    ])
    assert 5 not in _rows(sql, params)


def test_parameters_are_scoped_per_rule():
    """Two rules may use the same parameter name without colliding."""
    sql, params = compile_rules([
        Rule(Effect.ALLOW, "n = {v}", {"v": 3}),
        Rule(Effect.ALLOW, "n = {v}", {"v": 6}),
    ])
    assert set(params.values()) == {3, 6}
    assert _rows(sql, params) == [3, 6]


def test_single_allow_needs_no_extra_grouping():
    sql, _ = compile_rules([Rule(Effect.ALLOW, "n = 1")])
    assert sql == "(n = 1)"


def test_explain_reports_reasons_in_order():
    reasons = explain([
        Rule(Effect.ALLOW, "n < 2", why="own record"),
        Rule(Effect.DENY, "n = 1", why="routed elsewhere"),
        Rule(Effect.ALLOW, "n = 9"),  # no reason — omitted
    ])
    assert reasons == ["allow: own record", "deny: routed elsewhere"]
