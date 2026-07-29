"""SQLite store. Every read goes through the compiled predicate — there is no
second path.

The gate this module exists to pass: **hidden rows must not leak through a
COUNT, a filter, a sort order, or an empty state.** Each of those is a real leak
and each fails differently:

* *count* — the classic. Fetch the visible rows, take ``len()``, and you have
  told the truth. Fetch all rows, filter in Python, and you have shipped the
  hidden ones to the client before hiding them. So ``count`` here is a SQL
  ``COUNT(*)`` under the same predicate, and never a length in Python.
* *filter* — a caller-supplied ``WHERE`` is ANDed *inside* the authorization
  predicate, never ORed and never substituted. Narrowing a query can hide rows
  from yourself; it can never reveal one.
* *sort* — ordering columns come from an allowlist, so a sort cannot be used to
  smuggle a subquery, and ``LIMIT``/``OFFSET`` apply after the predicate, so
  page boundaries do not count what they do not show.
* *empty state* — a subject you may not see must be indistinguishable from a
  subject who does not exist. This is the one people forget, and it is the one
  that matters most, because a distinguishable refusal turns opting out into
  the signal.

Stdlib only. Nothing in this module opens a socket, and nothing imports
anything that could.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from . import schema
from .policy import Policy, Principal
from .rules import compile_rules

#: Columns a caller may sort by. An allowlist rather than an escape: quoting a
#: caller-supplied ORDER BY correctly is possible and is not worth doing when
#: the set of legitimate sorts is this small.
SORTABLE = frozenset({"id", "subject_id", "band", "created_at"})


@dataclass(frozen=True)
class Fact:
    id: int
    subject_id: str
    band: int
    payload: "str | None"
    instruction: "str | None"
    source: str


class Store:
    """Authorized reads over the facts table.

    Pass a connection (so consent, seals and domain data share one file and are
    backed up as a unit) or a path. Pass a Policy to change the rules; the store
    itself contains no notion of who may see what.
    """

    def __init__(self, conn: "sqlite3.Connection | str" = ":memory:",
                 policy: "Policy | None" = None) -> None:
        self._conn = sqlite3.connect(conn) if isinstance(conn, str) else conn
        self._conn.execute("PRAGMA foreign_keys = ON")
        self.policy = policy or Policy()
        schema.apply(self._conn)

    @property
    def connection(self) -> sqlite3.Connection:
        """The underlying connection, so a seal ledger can share the transaction."""
        return self._conn

    # ── the predicate every read shares ─────────────────────────────────────
    def predicate(self, principal: Principal,
                  extra: "str | None" = None,
                  extra_params: "dict | None" = None) -> "tuple[str, dict]":
        """Compile ``principal``'s rules, ANDed with an optional caller filter.

        The caller's filter is a further narrowing and is parenthesised so its
        internal ORs cannot escape into the authorization predicate. There is no
        argument that widens the result set; that is not an omission.
        """
        sql, params = compile_rules(self.policy.rules(principal))
        if extra:
            sql = f"({sql}) AND ({extra})"
            params = {**params, **(extra_params or {})}
        return sql, params

    # ── reads ───────────────────────────────────────────────────────────────
    def visible(self, principal: Principal, *,
                where: "str | None" = None,
                params: "dict | None" = None,
                order_by: str = "id",
                descending: bool = False,
                limit: "int | None" = None,
                offset: int = 0) -> "list[Fact]":
        if order_by not in SORTABLE:
            raise ValueError(f"cannot sort by {order_by!r}; allowed: {sorted(SORTABLE)}")

        predicate, bound = self.predicate(principal, where, params)
        bound.update(self.policy.projection_params(principal))

        sql = (
            f"SELECT facts.id, facts.subject_id, facts.band,"
            f" {self.policy.projection(principal)} AS payload,"
            f" facts.instruction, facts.source"
            f" FROM facts WHERE {predicate}"
            f" ORDER BY facts.{order_by} {'DESC' if descending else 'ASC'}"
        )
        if limit is not None:
            sql += " LIMIT :_limit OFFSET :_offset"
            bound.update({"_limit": int(limit), "_offset": int(offset)})

        return [Fact(*row) for row in self._conn.execute(sql, bound)]

    def count(self, principal: Principal, *,
              where: "str | None" = None,
              params: "dict | None" = None) -> int:
        """``COUNT(*)`` under the authorization predicate.

        The count is computed by SQLite over rows this principal may see. It is
        never ``len()`` of a fetched list, because that shape requires the
        hidden rows to have been read first.
        """
        predicate, bound = self.predicate(principal, where, params)
        return self._conn.execute(
            f"SELECT COUNT(*) FROM facts WHERE {predicate}", bound
        ).fetchone()[0]

    def subjects(self, principal: Principal) -> "list[str]":
        """Distinct subjects with at least one visible row.

        Subjects with nothing visible are absent from this list rather than
        present and empty. An empty slot is a disclosure: it says a person
        exists and you may not see them, which is most of what you wanted to
        know.
        """
        predicate, bound = self.predicate(principal)
        return [
            r[0] for r in self._conn.execute(
                f"SELECT DISTINCT facts.subject_id FROM facts"
                f" WHERE {predicate} ORDER BY facts.subject_id", bound
            )
        ]

    # ── writes ──────────────────────────────────────────────────────────────
    def record_fact(self, subject_id: str, band: int, source: str, *,
                    payload: "str | None" = None,
                    instruction: "str | None" = None) -> int:
        """Insert a fact. Rejected by the schema if ``source`` is blank."""
        cur = self._conn.execute(
            "INSERT INTO facts(subject_id, band, payload, instruction, source)"
            " VALUES (?, ?, ?, ?, ?)",
            (subject_id, int(band), payload, instruction, source),
        )
        self._conn.commit()
        return cur.lastrowid

    def record_grant(self, subject_id: str, grantee_id: str, band: int,
                     state: str, source: str, *,
                     sealed_by: "str | None" = None) -> int:
        """Insert or replace a grant. A sealed grant without a signer is refused."""
        cur = self._conn.execute(
            "INSERT INTO grants(subject_id, grantee_id, band, state, sealed_by, source)"
            " VALUES (?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(subject_id, grantee_id) DO UPDATE SET"
            "   band = excluded.band, state = excluded.state,"
            "   sealed_by = excluded.sealed_by, source = excluded.source",
            (subject_id, grantee_id, int(band), state, sealed_by, source),
        )
        self._conn.commit()
        return cur.lastrowid

    def revoke(self, subject_id: str, grantee_id: str) -> None:
        """Silent revocation. The grantee is not told, and nothing notifies them.

        Implemented as a delete rather than a state change so no residue of the
        former grant is readable. The disclosure ledger, which lives beside this
        store, is where the history belongs — not in the table the resolver
        reads on every query.
        """
        self._conn.execute(
            "DELETE FROM grants WHERE subject_id = ? AND grantee_id = ?",
            (subject_id, grantee_id),
        )
        self._conn.commit()
