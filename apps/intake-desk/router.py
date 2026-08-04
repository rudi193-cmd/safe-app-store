"""The routing pass.

**The router never adjudicates.** It does four things and then stops:

  1. resolve      — what entities, dates, places does this claim touch
  2. corroborate  — who else in the vault said something about this, and do
                    they agree
  3. sequence     — where does it sit in time, relative to related claims
  4. declare the gap — what could not be checked by any source that could exist

The output is a docket. A human rules. Nothing in this module writes
`ruled_by`, `confidence`, or any terminal state — `uncheckable` is *proposed*
here and confirmed by a person in `desk.mark_uncheckable`, because a machine
deciding that no record could exist is a machine deciding something.

A confident wrong answer about somebody's grandfather ends the product, so the
refusal contract below is fixed language, and `tests/test_router.py` holds it
with a vocabulary test over these exact strings. The router is built to be
boring and correct at the boundary.

No model, no network. Corroboration is retrieval and comparison over the local
vault. Claim extraction may one day use a model — `extract_entities` is the
seam for that — but nothing downstream of it may.
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field

import desk

# ── the refusal contract (spec §6) ─────────────────────────────────────────────
#
# The five sentences are the router's entire vocabulary of conclusion, and they
# live in vocabulary.py — the desk queue has to recognise a proposed gap without
# importing the thing that proposed it, and a contract owned by the component it
# constrains is not much of a contract. Re-exported here so callers of the
# router read them where they are used.

from vocabulary import (  # noqa: F401
    CONTRADICTED,
    CORROBORATED,
    FORBIDDEN,
    NO_SOURCE,
    UNCHECKABLE,
    UNCORROBORATED,
    verdict_language,
)


class RouterError(Exception):
    pass


# ── 1. resolve ────────────────────────────────────────────────────────────────

_YEAR = re.compile(r"\b(1[6-9]\d{2}|20\d{2})\b")
_PROPER = re.compile(r"\b([A-Z][a-z]{1,}(?:['’][A-Za-z]+)?(?:\s+[A-Z][a-z]{1,})*)\b")

# Words that start sentences and are not entities. Deliberately short: this
# resolver is naive on purpose and says so. Precision here is the job of a
# model-assisted resolver later; the seam is extract_entities(), and nothing
# downstream of it is allowed to become less careful because it improved.
_STOP = frozenset({
    "The", "A", "An", "It", "He", "She", "They", "We", "I", "You", "That",
    "This", "There", "Then", "But", "And", "Nobody", "Somebody", "Someone",
    "Everyone", "When", "What", "Who", "Where", "Why", "How", "After",
    "Before", "Once", "Never", "Always", "His", "Her", "Their", "Our", "My",
})


def extract_entities(text: str) -> tuple[str, ...]:
    """Candidate entities in a claim: proper-noun runs and years.

    Deliberately naive, and named as such. It is the seam a model-assisted
    resolver replaces — the one place in the router where a model would be
    legitimate, because it proposes what to look up rather than concluding
    anything about what is found.
    """
    found: list[str] = []
    for match in _PROPER.finditer(text):
        token = match.group(1)
        head = token.split()[0]
        if head in _STOP:
            token = " ".join(token.split()[1:])
        if token and token not in _STOP:
            found.append(token)
    found += _YEAR.findall(text)
    seen: dict[str, None] = {}
    for item in found:
        seen.setdefault(item.strip(), None)
    return tuple(seen)


# ── 3. sequence ───────────────────────────────────────────────────────────────

def _year_of(value: str | None) -> int | None:
    """The year in a fuzzy date. "1998", "1998-06?", "summer 1998" all resolve.

    Fuzzy time is how people actually date things, and it is more reliable than
    the precise year they will guess if pushed (spec §13.4). The router reads
    what it can and stays quiet about the rest.
    """
    if not value:
        return None
    match = _YEAR.search(value)
    return int(match.group(1)) if match else None


# ── the finding ───────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Finding:
    """What the routing pass found. Evidence and gaps — never a verdict."""

    claim_id: str
    status: str  # corroborated | contradicted | uncorroborated
                 # | no_source_found | uncheckable_proposed
    entities: tuple[str, ...] = ()
    corroborating: tuple[str, ...] = ()
    contradicting: tuple[str, ...] = ()
    independent_narrators: tuple[str, ...] = ()
    timeline: tuple[tuple[str, int], ...] = ()
    detail: tuple[str, ...] = field(default=())

    def sentence(self) -> str:
        """The router's conclusion, in the only words it is allowed."""
        if self.status == "corroborated":
            return CORROBORATED.format(n=len(self.independent_narrators))
        if self.status == "contradicted":
            a, b = (self.detail + ("", ""))[:2]
            return CONTRADICTED.format(a=a, b=b)
        if self.status == "uncheckable_proposed":
            return UNCHECKABLE
        if self.status == "uncorroborated":
            return UNCORROBORATED
        return NO_SOURCE


# ── 4. declare the gap ────────────────────────────────────────────────────────

# Interior state, in the first person, with no witness by construction: a
# feeling, a private thought, a thing nobody was told. The router only ever
# *proposes* this — desk.mark_uncheckable requires a human ruler, because
# confirming that a gap is real is work, and it is a person's work.
_INTERIOR = re.compile(
    r"\b("
    r"i (?:felt|thought|believed|knew|wanted|hoped|feared|wondered|assumed)"
    r"|i (?:never|didn'?t|did not) (?:told?|tell|say|said|mention)"
    r"|(?:nobody|no one|noone) (?:knew|noticed|saw|heard|was told)"
    r"|(?:was|were|felt) (?:scared|afraid|ashamed|relieved|proud|angry)"
    r"|in (?:my|his|her|their) head"
    r")\b",
    re.IGNORECASE,
)


def proposes_uncheckable(text: str) -> bool:
    return bool(_INTERIOR.search(text))


# ── 2. corroborate, and the pass itself ───────────────────────────────────────

def _related(conn: sqlite3.Connection, claim: sqlite3.Row, entities: tuple[str, ...]):
    """Other claims in the vault touching any of the same entities.

    Retrieval and comparison, not inference. A claim is related when the words
    it is about overlap — nothing here decides what the overlap means.
    """
    if not entities:
        return []
    rows = conn.execute(
        "SELECT c.*, s.narrator_id FROM claims c JOIN statements s ON s.id = c.statement_id"
        " WHERE c.id != ? AND c.state != 'withheld'",
        (claim["id"],),
    ).fetchall()
    out = []
    for row in rows:
        other = set(extract_entities(row["assertion"]))
        if other & set(entities):
            out.append(row)
    return out


def route(conn: sqlite3.Connection, claim_id: str, *, write_docket: bool = True) -> Finding:
    """Run the four passes over one claim and return the finding.

    Writes docket entries as a side effect (that is the deliverable), and
    moves `filed` -> `routed`. It writes nothing else: no ruling, no
    confidence, no terminal state.
    """
    claim = conn.execute(
        "SELECT c.*, s.narrator_id, s.body FROM claims c"
        " JOIN statements s ON s.id = c.statement_id WHERE c.id = ?",
        (claim_id,),
    ).fetchone()
    if claim is None:
        raise RouterError(f"no such claim: {claim_id!r}")

    entities = extract_entities(claim["assertion"])
    related = _related(conn, claim, entities)
    year = _year_of(claim["occurred_at"])

    corroborating: list[str] = []
    contradicting: list[str] = []
    narrators: list[str] = []
    detail: list[str] = []
    timeline: list[tuple[str, int]] = []

    for row in related:
        other_year = _year_of(row["occurred_at"])
        if other_year is not None:
            timeline.append((row["id"], other_year))
        # A comparison the router can actually make without semantics: two
        # claims about the same entities, dated to different years. That is a
        # disagreement about the record, and it is surfaced, never settled.
        if year is not None and other_year is not None and year != other_year:
            contradicting.append(row["id"])
            detail.append(f"{claim['narrator_id']} says {claim['occurred_at']}")
            detail.append(f"{row['narrator_id']} says {row['occurred_at']}")
        elif row["narrator_id"] != claim["narrator_id"]:
            # Independence is the whole point: a second telling by the same
            # narrator is the same source saying it twice.
            corroborating.append(row["id"])
            if row["narrator_id"] not in narrators:
                narrators.append(row["narrator_id"])

    if contradicting:
        status = "contradicted"
    elif len(narrators) >= 1:
        # ">= 2 independent agreeing sources" counts the narrator of this claim
        # plus every distinct other narrator who said something compatible.
        status = "corroborated"
        narrators = [claim["narrator_id"]] + narrators
    elif proposes_uncheckable(claim["assertion"]) or proposes_uncheckable(
        claim["body"][claim["span_start"]:claim["span_end"]]
    ):
        status = "uncheckable_proposed"
    elif related:
        status = "uncorroborated"
    else:
        status = "no_source_found"

    finding = Finding(
        claim_id=claim_id,
        status=status,
        entities=entities,
        corroborating=tuple(corroborating),
        contradicting=tuple(contradicting),
        independent_narrators=tuple(narrators),
        timeline=tuple(sorted(timeline, key=lambda t: t[1])),
        detail=tuple(detail[:2]),
    )

    if write_docket:
        _record(conn, claim_id, finding)
    return finding


def _record(conn: sqlite3.Connection, claim_id: str, finding: Finding) -> None:
    """Turn a finding into docket entries. Evidence, with the source named."""
    for other in finding.contradicting:
        desk.add_docket_entry(
            conn, claim_id=claim_id, relation="contradicts", source_kind="vault",
            source_ref=f"claim:{other}", excerpt=finding.sentence(), found_by="router",
        )
    for other in finding.corroborating:
        desk.add_docket_entry(
            conn, claim_id=claim_id, relation="corroborates", source_kind="vault",
            source_ref=f"claim:{other}", excerpt=finding.sentence(), found_by="router",
        )
    if finding.status in ("no_source_found", "uncheckable_proposed", "uncorroborated"):
        desk.add_docket_entry(
            conn, claim_id=claim_id, relation="no_source_found", source_kind="vault",
            source_ref=None, excerpt=finding.sentence(), found_by="router",
        )


def route_all(conn: sqlite3.Connection) -> list[Finding]:
    """Sweep every claim nobody has routed yet."""
    rows = conn.execute("SELECT id FROM claims WHERE state = 'filed'").fetchall()
    return [route(conn, row["id"]) for row in rows]
