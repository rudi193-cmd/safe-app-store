"""The refusal contract.

The five sentences the router is allowed to conclude with, and the words it
may never say. This lives in its own module, imported by both the router and
the desk queue, because a contract that constrains a component should not be
owned by that component — and because the queue has to recognise a proposed
gap without importing the router that proposed it.

Nothing here formats a verdict. There is no sentence available for "this is
true", and that absence is the design.
"""
from __future__ import annotations

import re

CORROBORATED = "Corroborated by {n} sources."
CONTRADICTED = "Contradicted. {a}; {b}."
NO_SOURCE = "No source found. This is checkable — nobody has checked it."
UNCHECKABLE = "Uncheckable. No record of this could exist."
UNCORROBORATED = "Uncorroborated. Only the narrator asserts this."

SENTENCES = (CORROBORATED, CONTRADICTED, NO_SOURCE, UNCHECKABLE, UNCORROBORATED)

#: Words the router must never emit. It reports evidence, not conclusions.
FORBIDDEN = (
    "verified", "unverified", "true", "false", "fact", "proven", "disproven",
    "confirmed", "debunked", "accurate", "inaccurate", "correct", "incorrect",
    "wrong", "lie", "lying", "hoax", "credible", "trustworthy", "reliable",
)

_FORBIDDEN_RE = re.compile(r"\b(" + "|".join(FORBIDDEN) + r")\b", re.IGNORECASE)


def verdict_language(text: str) -> str | None:
    """The first verdict word in `text`, or None.

    Whole words only, deliberately: a narrator called Charlie or a place on
    Trueman Street must not trip a gate about the router's vocabulary. The
    check is on what the router *says*, not on what people are named.
    """
    match = _FORBIDDEN_RE.search(text or "")
    return match.group(1).lower() if match else None
