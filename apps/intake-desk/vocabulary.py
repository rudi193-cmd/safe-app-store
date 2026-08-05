"""The refusal contract.

Every sentence the router is allowed to conclude with, and the words it may
never say. This lives in its own module, imported by both the router and the
desk queue, because a contract that constrains a component should not be owned
by that component.

**There is no sentence for agreement, and that is deliberate.**

An earlier version had one — "Corroborated by {n} sources." — and an
adversarial pass measured it wrong on 89% of the corroborations it produced
over a realistic corpus. Relatedness here is entity overlap; entity overlap
cannot see negation, so "Miller's Bar never had a back room" was reported as
corroborating "Miller's Bar had a back room". Retrieval can honestly say
*these claims are about the same things*. It cannot say *they agree*. So the
router now hands the reader candidates and stops, and the only thing that can
promote a candidate to agreement is a person.
"""
from __future__ import annotations

import re

#: Retrieval found other claims about the same things. It says nothing about
#: whether they agree, because it cannot know.
RELATED = "Related claims found: {n}. Read them."

#: Dated accounts that cannot all be right. Names every one of them.
CONTRADICTED = "Contradicted. {accounts}."

#: The same narrator dating the same thing two ways. Not a contradiction
#: between sources — one person's memory moving — and it must not wear the
#: sentence reserved for conflicting sources.
SELF_INCONSISTENT = "The narrator dated this two ways: {accounts}."

NO_SOURCE = "No source found. This is checkable — nobody has checked it."
UNCHECKABLE = "Uncheckable. No record of this could exist."
UNCORROBORATED = "Uncorroborated. Only the narrator asserts this."

#: Nothing was looked up, so nothing may be said about the vault.
UNRESOLVED = "Nothing to look up: no entity could be resolved from this claim."

SENTENCES = (RELATED, CONTRADICTED, SELF_INCONSISTENT, NO_SOURCE,
             UNCHECKABLE, UNCORROBORATED, UNRESOLVED)

#: Words the router must never emit. It reports evidence, not conclusions.
FORBIDDEN = (
    "verified", "unverified", "true", "false", "fact", "proven", "disproven",
    "confirmed", "corroborated", "debunked", "accurate", "inaccurate",
    "correct", "incorrect", "wrong", "lie", "lying", "hoax", "credible",
    "trustworthy", "reliable",
)

_FORBIDDEN_RE = re.compile(r"\b(" + "|".join(FORBIDDEN) + r")\b", re.IGNORECASE)

#: What may survive from a narrator-supplied string into a router sentence.
#: Free text reached `CONTRADICTED.format(...)` unfiltered before, so an
#: `--occurred-at` of "2001 — and the record proves slappy is lying" became
#: part of the router's own conclusion and left in the export.
_UNSAFE = re.compile(r"[^\w\s./?'\[\]-]")
_FIELD_MAX = 48


def sanitize(value: str | None) -> str:
    """Reduce a narrator-supplied field to something that cannot forge a
    sentence: no punctuation that ends or joins clauses, no newlines, bounded
    length."""
    if not value:
        return "no date given"
    flat = " ".join(str(value).split())
    # Verdict words are redacted here rather than only refused at write time.
    # A date field is not a place for prose, and one narrator typing "lying"
    # into --occurred-at should not be able to stop the desk from routing.
    flat = _FORBIDDEN_RE.sub("[redacted]", flat)
    cleaned = _UNSAFE.sub("", flat).strip()
    if len(cleaned) > _FIELD_MAX:
        cleaned = cleaned[:_FIELD_MAX].rstrip() + "…"
    return cleaned or "no date given"


def verdict_language(text: str) -> str | None:
    """The first verdict word in `text`, or None.

    Whole words only, deliberately: a narrator called Charlie or a place on
    Trueman Street must not trip a gate about the router's vocabulary.

    This is a backstop, not a guarantee. "Deputy Ray Kolb (established the
    actual date from the blotter) says 2001" is a complete verdict containing
    none of these words. The real defences are `sanitize` above and the fact
    that the contract has no agreement sentence at all; this catches the
    careless case, and the router calls it on every sentence it writes.
    """
    match = _FORBIDDEN_RE.search(text or "")
    return match.group(1).lower() if match else None
