"""Entity and date resolution.

Its own module because both the desk (which persists what a claim touches) and
the router (which looks claims up by it) need it, and the router already
imports the desk. Nothing here concludes anything — it only decides what is
worth looking up.

Deliberately naive, and named as such. This is the one seam in the pipeline
where a model would be legitimate: it proposes what to look up rather than
saying anything about what is found.
"""
from __future__ import annotations

import re

_YEAR = re.compile(r"\b(1[6-9]\d{2}|20\d{2})\b")
_PROPER = re.compile(r"\b([A-Z][a-z]{1,}(?:['’][A-Za-z]+)?(?:\s+[A-Z][a-z]{1,})*)\b")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")

# Words that begin sentences and are not entities.
#
# This list is long because it has to be. A short list let sentence-initial
# prepositions through as entities, so any two claims from two narrators that
# merely started with the same word — "In 1962 my father shipped out." and
# "In the winter the pipes froze." — came back related on a shared entity of
# ("In",). An entity key that matches on English grammar is not an entity key.
_STOP = frozenset("""
A An And After Also Although Always As At Back Because Before Both But By
Down During Each Either Even Every Everybody Everyone For From He Her Here
His How However I If In Into It Its Just Later Like Many Maybe More Most My
Never Next No Nobody None Noone Not Nothing Now Of Off On Once One Only Or
Other Our Out Over Perhaps Right She Since So Some Somebody Someone Something
Sometimes Still Such Than That The Their Then There These They This Those
Though Through To Under Until Up Us Very We Well What When Where Whether
Which While Who Why With Without Would Yes Yet You Your
""".split())


def extract_entities(text: str) -> tuple[str, ...]:
    """Candidate entities: proper-noun runs, normalised for lookup.

    Bare years are NOT entities. A year is the noisiest possible join key —
    it relates a school burning down to somebody buying a truck — and years
    are still read for sequencing by `year_span`, where they belong.
    """
    found: list[str] = []
    for sentence in _SENTENCE_SPLIT.split(text):
        for match in _PROPER.finditer(sentence):
            token = match.group(1)
            words = token.split()
            # A capitalised word at the start of a sentence is only an entity
            # when the run continues past it ("Miller's Bar had...") — a lone
            # leading capital is indistinguishable from grammar.
            if match.start() == 0 and len(words) == 1:
                continue
            if words[0] in _STOP:
                words = words[1:]
            token = " ".join(words)
            if token and token not in _STOP and len(token) > 1:
                found.append(token)
    seen: dict[str, None] = {}
    for item in found:
        seen.setdefault(item.strip(), None)
    return tuple(seen)


def year_span(value: str | None) -> tuple[int, int] | None:
    """The interval a fuzzy date covers, or None if no year is readable.

    An interval, not a point. "1998-2001" is a narrator saying *somewhere in
    here* — collapsing it to 1998 turned an honest range into a contradiction
    with anyone who said 2001, which is the exact opposite of why spec §13.4
    accepts fuzzy dates at all.

    "summer 1998" -> (1998, 1998) · "1998-2001" -> (1998, 2001) · "the 1990s"
    -> (1990, 1999) · "mid-90s" -> None (unreadable, and saying so is correct).
    """
    if not value:
        return None
    decade = re.search(r"\b(1[6-9]\d0|20\d0)s\b", value)
    if decade:
        start = int(decade.group(1))
        return (start, start + 9)
    years = [int(y) for y in _YEAR.findall(value)]
    if not years:
        return None
    return (min(years), max(years))


def disjoint(a: tuple[int, int] | None, b: tuple[int, int] | None) -> bool:
    """True only when two dated accounts cannot both be right.

    Overlap is not agreement — it is the absence of a demonstrable conflict,
    which is all a date comparison can honestly establish.
    """
    if a is None or b is None:
        return False
    return a[1] < b[0] or b[1] < a[0]
