"""Data-classification bands.

Every fact the platform stores is about a person, and every one carries a band.
The band is a column from the first migration, not a decoration added later:
you can add the column to a schema afterwards, but you cannot add it to data
that was written without it.

The bands are ordered by sensitivity, and the order is load-bearing — a grant
names the highest band it authorizes and covers everything below it. Do not
reorder these values; existing rows carry the integers.
"""
from __future__ import annotations

from enum import IntEnum


class Band(IntEnum):
    """L0 through L6, least to most sensitive."""

    SELF = 0             # the member's own view of their own record
    ROSTER = 1           # name, section, part assignment — the org chart
    CRAFT = 2            # rehearsal notes, technique, what a section leader teaches to
    ACCOMMODATION = 3    # what someone needs. NEVER forwarded as a fact — see below.
    HEALTH = 4           # medical. Named persons only, never roles.
    SAFEGUARDING = 5     # routed, never received. Nothing here is served by this app.
    FAMILY = 6           # family and financial circumstance


#: At and above this band the platform serves the *derived instruction* and never
#: the underlying fact. A section leader learns "rotate this member out every
#: twenty minutes"; they do not learn why. The mechanism is a projection in the
#: SELECT list (see policy.Policy.projection) rather than a promise in a doc.
DERIVE_AT = Band.ACCOMMODATION

#: Bands this application refuses to serve at all, to anyone, under any grant.
#: L5 is routed to the people whose job it is and never received here: in every
#: leadership-implicating case on the public record, surfacing was external, so
#: an intake would digitise a broken path rather than repair it.
NEVER_SERVED = frozenset({Band.SAFEGUARDING})


def parse(value: "int | str | Band") -> Band:
    """Coerce a stored integer or a name to a Band, rejecting anything else.

    Fails loudly. A band that cannot be resolved is not defaulted to SELF — a
    silent downgrade to the least sensitive value is exactly the wrong failure
    direction for this column.
    """
    if isinstance(value, Band):
        return value
    if isinstance(value, int):
        return Band(value)
    return Band[str(value).strip().upper()]
