"""Authorization rules and the compiler that turns them into one SQL predicate.

The whole point of this module is a precedence rule that is easy to state and
easy to get wrong:

    (allow1 OR allow2 OR ...) AND NOT (deny1 OR deny2 OR ...)

Denials apply to the *union* of the allowances, not pairwise, and not before
them. Getting that backwards — evaluating a deny against a single allow, or
letting a later allow re-open something an earlier deny closed — is the single
most likely way to rebuild the leak this app exists to prevent.

The compiler is deliberately dumb: it emits a fragment and a parameter dict and
knows nothing about bands, grants or people. Policy lives in policy.py, so this
file can be read in one sitting and checked by eye.

Stdlib only. No SQL is executed here; nothing here touches a connection.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Effect(Enum):
    ALLOW = "allow"
    DENY = "deny"


@dataclass(frozen=True)
class Rule:
    """One predicate fragment, its parameters, and why it exists.

    ``sql`` uses named placeholders written *without* the leading colon and
    scoped per rule at compile time, so two rules may both use a parameter
    called ``viewer`` without colliding. Write ``subject_id = {viewer}`` and the
    compiler renders ``subject_id = :r0_viewer``.

    ``why`` is not decoration. It is what an audit log records when a row is
    withheld, and what a support conversation quotes when a director asks why
    they cannot see something.
    """

    effect: Effect
    sql: str
    params: dict = field(default_factory=dict)
    why: str = ""

    def render(self, index: int) -> tuple[str, dict]:
        scoped = {f"r{index}_{k}": v for k, v in self.params.items()}
        placeholders = {k: f":r{index}_{k}" for k in self.params}
        return self.sql.format(**placeholders), scoped


#: The fail-closed predicate. A principal with no allow rules sees nothing —
#: not "everything", not "their own rows by accident". SQLite has no boolean
#: literal, so 0 and 1 stand in.
DENY_ALL = "0"
ALLOW_ALL = "1"


def compile_rules(rules: "list[Rule]") -> tuple[str, dict]:
    """Compile rules to ``(sql_predicate, params)``.

    Empty allow set → ``DENY_ALL``. That is the behaviour to check first if you
    are ever unsure whether this module is working: a principal the policy does
    not recognise must see zero rows, and must reach that state by rule rather
    than by exception.
    """
    allows: list[str] = []
    denies: list[str] = []
    params: dict = {}

    for index, rule in enumerate(rules):
        sql, scoped = rule.render(index)
        params.update(scoped)
        (allows if rule.effect is Effect.ALLOW else denies).append(f"({sql})")

    if not allows:
        return DENY_ALL, {}

    predicate = " OR ".join(allows)
    if len(allows) > 1:
        predicate = f"({predicate})"

    if denies:
        # The parentheses around the joined denies are what make this a negation
        # of the union rather than of the first term. Do not remove them.
        predicate = f"{predicate} AND NOT ({' OR '.join(denies)})"

    return predicate, params


def explain(rules: "list[Rule]") -> list[str]:
    """Human-readable reasons, allows first, for audit output and support."""
    return [f"{r.effect.value}: {r.why}" for r in rules if r.why]
