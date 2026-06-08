"""Query intent classification for AskJeles (Jeeves-style routing)."""

from __future__ import annotations

import re
from enum import Enum

_NAV_HINTS = re.compile(
    r"\b(near me|nearby|closest|directions?|hours|address|locations?|"
    r"store locator|find a|where is|where are|open now|phone number|"
    r"map quest|mapquest)\b",
    re.IGNORECASE,
)
_LOCAL_BRAND = re.compile(
    r"\b(trader joe'?s?|whole foods|costco|walmart|target|starbucks|"
    r"home depot|lowe'?s?|cvs|walgreens|mcdonald'?s?)\b",
    re.IGNORECASE,
)
_RESEARCH_HINTS = re.compile(
    r"\b(author|writer|novel|book|poem|research|paper|study|theorem|"
    r"history of|according to|cite|citation|primary source|archive)\b",
    re.IGNORECASE,
)


class QueryClass(str, Enum):
    NAVIGATIONAL = "navigational"
    RESEARCH = "research"
    GENERAL = "general"


def classify(question: str) -> QueryClass:
    q = (question or "").strip()
    if not q:
        return QueryClass.GENERAL
    if _NAV_HINTS.search(q) or _LOCAL_BRAND.search(q):
        return QueryClass.NAVIGATIONAL
    if _RESEARCH_HINTS.search(q):
        return QueryClass.RESEARCH
    return QueryClass.GENERAL


def skip_spell_check(question: str) -> bool:
    """Brand/navigational queries should not be token-corrected."""
    q = (question or "").strip()
    if not q:
        return False
    if classify(q) == QueryClass.NAVIGATIONAL:
        return True
    if _LOCAL_BRAND.search(q):
        return True
    if re.search(r"\bnear me\b", q, re.IGNORECASE):
        return True
    return False
