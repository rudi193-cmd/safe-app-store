"""The routing pass.

**The router never adjudicates, and it no longer claims agreement either.**
It does four things and then stops:

  1. resolve      — what entities and dates does this claim touch
  2. retrieve     — which other claims in the vault are about the same things
  3. sequence     — can the dated accounts all be right
  4. declare the gap — what could not be checked by any source that could exist

The output is a docket of candidates and conflicts. A human rules.

What changed, and why it matters more than anything else in this module: there
used to be a fifth thing, "corroborate", which reported "Corroborated by N
sources." whenever another narrator's claim shared an entity. An adversarial
pass measured that wrong on 89% of the corroborations it produced. Entity
overlap cannot see negation, so a source that *denied* a claim was counted as
confirming it. Retrieval can honestly say *these are about the same things*;
it cannot say *they agree*. Only a person can promote a candidate to
agreement, so the sentence is gone.

Nothing here writes `ruled_by`, `confidence`, or a terminal state.
`uncheckable` is *proposed* and confirmed by a person in
`desk.mark_uncheckable`, because a machine deciding that no record could exist
is a machine deciding something.

No model, no network.
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass

import desk
import vocabulary
from entities import disjoint, extract_entities, year_span
from vocabulary import (  # noqa: F401  (re-exported: callers read them here)
    CONTRADICTED,
    NO_SOURCE,
    RELATED,
    SELF_INCONSISTENT,
    UNCHECKABLE,
    UNCORROBORATED,
    UNRESOLVED,
    sanitize,
    verdict_language,
)


class RouterError(Exception):
    pass


# ── declaring the gap ─────────────────────────────────────────────────────────
#
# First person, interior, with no witness by construction. Every clause is
# anchored to a first-person pronoun on purpose: the previous version matched
# "nobody knew/saw/was told …", which is a claim about the *world* and is
# usually checkable — "Nobody saw the truck leave the lot" is answered by the
# lot's cameras. Marking that uncheckable routes a checkable claim toward never
# being checked, under the strongest sentence in the contract.
_INTERIOR = re.compile(
    r"(?:^|[.!?]\s+|;\s*)i\s+(?:"
    r"felt|thought|believed|knew|wanted|hoped|feared|wondered|assumed"
    r"|never\s+(?:told|said|mentioned)"
    r"|didn'?t\s+(?:tell|say|mention)"
    r"|did\s+not\s+(?:tell|say|mention)"
    r"|was\s+(?:scared|afraid|ashamed|relieved|proud|angry|terrified|humiliated)"
    r")\b",
    re.IGNORECASE,
)


def proposes_uncheckable(text: str) -> bool:
    """Whether a claim looks like interior state nobody could witness.

    Conservative by design, and it only ever *proposes*. A false positive here
    is worse than a false negative: it buries a checkable claim in the queue
    bucket whose instruction is "confirm the gap and let it stand".
    """
    return bool(_INTERIOR.search(text or ""))


# ── the finding ───────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Finding:
    """What the routing pass found. Candidates, conflicts and gaps.

    There is no field, and no sentence, that asserts agreement.
    """

    claim_id: str
    status: str  # contradicted | self_inconsistent | uncheckable_proposed
                 # | related_found | uncorroborated | no_source_found | unresolved
    entities: tuple[str, ...] = ()
    related: tuple[str, ...] = ()
    contradicting: tuple[str, ...] = ()
    accounts: tuple[str, ...] = ()
    timeline: tuple[tuple[str, int], ...] = ()

    def sentence(self) -> str:
        """The router's conclusion, in the only words it is allowed."""
        if self.status == "contradicted":
            if not self.accounts:
                raise RouterError("contradicted with no accounts to name")
            return CONTRADICTED.format(accounts="; ".join(self.accounts))
        if self.status == "self_inconsistent":
            if not self.accounts:
                raise RouterError("self_inconsistent with no accounts to name")
            return SELF_INCONSISTENT.format(accounts="; ".join(self.accounts))
        if self.status == "uncheckable_proposed":
            return UNCHECKABLE
        if self.status == "related_found":
            return RELATED.format(n=len(self.related))
        if self.status == "uncorroborated":
            return UNCORROBORATED
        if self.status == "unresolved":
            return UNRESOLVED
        return NO_SOURCE


# ── retrieval ─────────────────────────────────────────────────────────────────

def _related(conn: sqlite3.Connection, claim: sqlite3.Row):
    """Other claims about the same things.

    Joins the persisted entity index rather than re-extracting entities over
    the whole table on every call — the old version was quadratic and measured
    at 139 seconds for a 500-claim sweep, which an archive with one shoebox of
    transcripts would exceed on its first afternoon.

    Excludes claims a human has already dealt with: `withheld` (revoked or
    asked), and `uncheckable` (a confirmed gap is not evidence for anything).
    """
    return conn.execute(
        "SELECT DISTINCT c.*, s.narrator_id FROM claim_entities e"
        " JOIN claims c ON c.id = e.claim_id"
        " JOIN statements s ON s.id = c.statement_id"
        " WHERE e.entity IN (SELECT entity FROM claim_entities WHERE claim_id = ?)"
        "   AND c.id != ?"
        "   AND c.state NOT IN ('withheld','uncheckable')"
        " ORDER BY c.id",
        (claim["id"], claim["id"]),
    ).fetchall()


def route(conn: sqlite3.Connection, claim_id: str, *, write_docket: bool = True) -> Finding:
    """Run the passes over one claim and return the finding.

    Writes docket entries as a side effect (that is the deliverable), replacing
    any the router wrote for this claim before, and moves `filed` -> `routed`.
    It writes nothing else.
    """
    claim = conn.execute(
        "SELECT c.*, s.narrator_id FROM claims c"
        " JOIN statements s ON s.id = c.statement_id WHERE c.id = ?",
        (claim_id,),
    ).fetchone()
    if claim is None:
        raise RouterError(f"no such claim: {claim_id!r}")

    ents = tuple(r["entity"] for r in conn.execute(
        "SELECT entity FROM claim_entities WHERE claim_id = ? ORDER BY entity", (claim_id,)))
    mine = year_span(claim["occurred_at"])
    me = sanitize(claim["narrator_id"])

    related: list[str] = []
    contradicting: list[str] = []
    self_conflict: list[str] = []
    accounts: dict[str, None] = {f"{me} says {sanitize(claim['occurred_at'])}": None}
    timeline: list[tuple[str, int]] = []
    others: list[str] = []

    for row in _related(conn, claim) if ents else []:
        theirs = year_span(row["occurred_at"])
        if theirs is not None:
            timeline.append((row["id"], theirs[0]))
        if disjoint(mine, theirs):
            entry = f"{sanitize(row['narrator_id'])} says {sanitize(row['occurred_at'])}"
            accounts.setdefault(entry, None)
            if row["narrator_id"] == claim["narrator_id"]:
                self_conflict.append(row["id"])
            else:
                contradicting.append(row["id"])
        else:
            related.append(row["id"])
            if row["narrator_id"] != claim["narrator_id"]:
                others.append(row["narrator_id"])

    # Precedence. The gap test sits above retrieval on purpose: a private
    # moment must not be talked over by whatever else happens to mention the
    # same town. Previously it sat below, and someone's "I never told anybody
    # how scared I was at Laconia" came back corroborated by a stranger who
    # said Laconia is up north.
    if contradicting:
        status = "contradicted"
    elif self_conflict:
        status = "self_inconsistent"
    elif proposes_uncheckable(claim["assertion"]):
        status = "uncheckable_proposed"
    elif not ents:
        # Nothing was looked up, so nothing may be said about the vault.
        # `No source found` asserts a fact about what is in there.
        status = "unresolved"
    elif related and others:
        status = "related_found"
    elif related:
        status = "uncorroborated"
    else:
        status = "no_source_found"

    finding = Finding(
        claim_id=claim_id,
        status=status,
        entities=ents,
        related=tuple(related),
        contradicting=tuple(contradicting + self_conflict),
        accounts=tuple(accounts) if status in ("contradicted", "self_inconsistent") else (),
        timeline=tuple(sorted(timeline, key=lambda t: t[1])),
    )

    if write_docket:
        _record(conn, claim_id, finding)
    return finding


def _record(conn: sqlite3.Connection, claim_id: str, finding: Finding) -> None:
    """Turn a finding into docket entries, replacing the router's previous pass.

    The sentence is checked against the forbidden vocabulary *here*, at the
    point it is written. The gate used to exist only in the test suite, which
    meant narrator-supplied text could carry a verdict into the docket and out
    through the export with nothing in the running system objecting.
    """
    sentence = finding.sentence()
    found = verdict_language(sentence)
    if found is not None:
        raise RouterError(
            f"refusing to write a docket entry containing {found!r} — "
            "the router reports evidence, not conclusions"
        )

    # Routing is idempotent: re-running replaced nothing before, so four runs
    # left four identical rows and the queue read whichever was stale.
    conn.execute(
        "DELETE FROM docket_entries WHERE claim_id = ? AND found_by = 'router'",
        (claim_id,),
    )
    conn.commit()

    for other in finding.contradicting:
        desk.add_docket_entry(
            conn, claim_id=claim_id, relation="contradicts", source_kind="vault",
            source_ref=f"claim:{other}", excerpt=sentence, found_by="router",
        )
    for other in finding.related:
        desk.add_docket_entry(
            conn, claim_id=claim_id, relation="contextualizes", source_kind="vault",
            source_ref=f"claim:{other}", excerpt=sentence, found_by="router",
        )
    if finding.status in ("no_source_found", "uncheckable_proposed",
                          "uncorroborated", "unresolved"):
        desk.add_docket_entry(
            conn, claim_id=claim_id, relation="no_source_found", source_kind="vault",
            source_ref=None, excerpt=sentence, found_by="router",
        )


def route_all(conn: sqlite3.Connection) -> list[Finding]:
    """Sweep every claim nobody has routed yet."""
    rows = conn.execute("SELECT id FROM claims WHERE state = 'filed'").fetchall()
    return [route(conn, row["id"]) for row in rows]
