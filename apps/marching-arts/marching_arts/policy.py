"""Who may see what, expressed as rules the compiler can turn into SQL.

Two ideas carry most of the weight here.

**Grants resolve per record, not per user.** Every leader is also a member. A
section leader is a grantee on their squad's rows and a subject on their own,
often in the same query, so authorization cannot be a property of the person.

**Only a sealed grant authorizes.** The state machine is Nestor's: a grant a
named human signed is *sealed*; anything the system inferred is *draft* and is
never acted on; a subject with no grant on file is *pending*, which is not a
denial to be rendered but an absence to be rendered as nothing. Draft and
pending are indistinguishable from the outside, and that is the point — if a
refusal looked different from a blank, opting out would become the signal and
everyone who declined would be marked by declining.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .bands import DERIVE_AT, NEVER_SERVED, Band
from .rules import Effect, Rule


class GrantState(Enum):
    """Nestor's cascade, applied to consent rather than to answers."""

    SEALED = "sealed"    # a named human signed this. The only state that authorizes.
    DRAFT = "draft"      # the system inferred it. Recorded, never acted on.
    PENDING = "pending"  # nothing on file. Renders as nothing, not as an empty slot.


@dataclass(frozen=True)
class Principal:
    """Whoever is asking. Roles are context, never authority on their own.

    ``roles`` cannot grant access to anything at or above :data:`bands.DERIVE_AT`
    — those bands are reachable only by a grant naming this principal
    individually. That is the "L4 is named persons only" decision, and it is
    enforced below rather than documented.
    """

    person_id: str
    roles: frozenset = field(default_factory=frozenset)


class Policy:
    """The default marching-program policy. Injectable; subclass to change it.

    A host that wants different rules supplies a different Policy. The store
    never inspects bands or grants itself, so there is exactly one place in the
    codebase where "who may see what" is decided.
    """

    #: Table holding grants. Referenced by correlated subquery so that grant
    #: revocation takes effect on the next read with no cache to invalidate.
    grants_table = "grants"

    def rules(self, principal: Principal) -> list[Rule]:
        rules = [
            # A person always sees their own record, at every band, with no
            # grant required. Consent governs disclosure to others; it does not
            # stand between someone and their own information.
            Rule(
                Effect.ALLOW,
                "subject_id = {viewer}",
                {"viewer": principal.person_id},
                "a person always sees their own record",
            ),
            # Someone else's row, only where a sealed grant names this viewer
            # and reaches at least this row's band. Correlated per row, which is
            # what makes this per-record rather than per-user.
            Rule(
                Effect.ALLOW,
                "EXISTS (SELECT 1 FROM "
                + self.grants_table
                + " g WHERE g.subject_id = facts.subject_id"
                "   AND g.grantee_id = {viewer}"
                "   AND g.state = {sealed}"
                "   AND g.band >= facts.band)",
                {"viewer": principal.person_id, "sealed": GrantState.SEALED.value},
                "a sealed grant from the subject reaches this row's band",
            ),
        ]

        if NEVER_SERVED:
            # Refused outright, above and before any grant. A grant that reaches
            # one of these bands does not open it — the deny is applied to the
            # union of allows, so no allow can win against it.
            rules.append(
                Rule(
                    Effect.DENY,
                    "facts.band IN ({bands})".format(
                        bands=", ".join(str(int(b)) for b in sorted(NEVER_SERVED))
                    ),
                    {},
                    "this band is routed to the people whose job it is, never served here",
                )
            )

        return rules

    def projection(self, principal: Principal) -> str:
        """SQL expression for the ``payload`` column.

        Derive the instruction, do not forward the fact. At and above
        :data:`bands.DERIVE_AT`, another person's payload is replaced with NULL
        in the SELECT list — the row is still visible, its ``instruction`` still
        readable, and the fact itself never leaves the database.

        Returning NULL rather than omitting the row is deliberate: a section
        leader needs to know there *is* an instruction to follow. What they must
        not learn is the diagnosis behind it.
        """
        return (
            "CASE WHEN facts.band >= {derive} AND facts.subject_id != :viewer "
            "THEN NULL ELSE facts.payload END"
        ).format(derive=int(DERIVE_AT))

    def projection_params(self, principal: Principal) -> dict:
        return {"viewer": principal.person_id}
