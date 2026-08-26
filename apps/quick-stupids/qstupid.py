"""Quick, stupid one-liners are sometimes the load-bearing ones.

Files this app's local ``CLAUDE.md`` "Rules that DO apply here" section
as verified jeles nuggets. The pattern lives in
:mod:`quick_stupids.core` (``libs/quick-stupids/``); this file supplies
only the ``QUESTIONS`` map and the source parser, so the next subject
app can reuse ``core.subject_app`` without touching either.

Subcommands (from ``core.subject_app``):
    seed    upsert each maxim as a nugget.
    check   search the seeded maxims for ones that bear on a given claim.
    list    print what's currently filed under this app's id prefix.
"""
from __future__ import annotations

import re
from pathlib import Path

from quick_stupids.core import subject_app

# The app owns its own CLAUDE.md. The source of principles is the local
# file, not the store's top-level law — a subject app files its own
# rules, and mixing the two would let one section drift while the other
# tried to speak for it.
APP_ROOT = Path(__file__).resolve().parent
CLAUDE_MD = APP_ROOT / "CLAUDE.md"
SECTION_HEADING = "## Rules that DO apply here"
NEXT_HEADING_PREFIX = "## "

QUESTIONS = {
    "Every guarantee is a mechanism or it is a wish.":
        "What makes a guarantee real rather than a wish?",
    "A gate that cannot fail is not a gate.":
        "How do you know a test is actually a gate?",
    "Coverage is a claim about the harness, not about the code.":
        "What does a green required check actually tell you?",
    "State the aggregation whenever you quote a statistic.":
        "What is required beside a statistic for it to travel?",
    "A test that does not run in CI is not a test.":
        "What counts as a test?",
    "Provenance is a state, not a score.":
        "How should the origin of an input be recorded?",
    "Absence is a recorded value, not a missing row.":
        "How should absence be represented in a record?",
    "Corrections land beside the record, never on top of it.":
        "Where should a correction go?",
    "The failure is never in the step you are watching.":
        "Where should you look for the cause of a wrong answer?",
}

_MAXIM_RE = re.compile(r"\*\*([^*]+?\.)\*\*\s*(.*?)(?=\n\n\*\*|\Z)", re.DOTALL)


def _section() -> str:
    text = CLAUDE_MD.read_text(encoding="utf-8")
    idx = text.find(SECTION_HEADING)
    if idx == -1:
        # Missing heading → seed reports 0 principles rather than crashing.
        # A renamed section is a maker decision the app should surface, not
        # a stack trace they have to read to figure out.
        return ""
    start = idx + len(SECTION_HEADING)
    tail = text[start:]
    end = tail.find(f"\n{NEXT_HEADING_PREFIX}")
    return tail[:end if end != -1 else None]


def _principles() -> dict[str, str]:
    out: dict[str, str] = {}
    for match in _MAXIM_RE.finditer(_section()):
        maxim = match.group(1).strip()
        rest = re.sub(r"\s+", " ", match.group(2)).strip()
        if maxim in QUESTIONS:
            out[QUESTIONS[maxim]] = f"{maxim} {rest}".strip()
    return out


def main(argv: list[str] | None = None) -> int:
    return subject_app(
        prog="qstupid",
        description=(
            "Seed jeles's corpus with the quick-stupid one-liners that "
            "govern this app, then query them."
        ),
        id_prefix="quick-stupids/founding/",
        tags=["founding", "quick-stupids"],
        source="file://apps/quick-stupids/CLAUDE.md#rules-that-do-apply-here",
        verified_by="rudi193@gmail.com",
        written_by="apps/quick-stupids/qstupid.py",
        principles=_principles(),
        no_hits_message=(
            "*without looking up* — nothing in the founding rules bears on that.\n"
            "*slight pause* You're not the first to ask. It may be uncatalogued."
        ),
        hits_header="That would be filed under:",
        hits_footer="It isn't lost. It's misfiled.",
        argv=argv,
    )


if __name__ == "__main__":
    raise SystemExit(main())
