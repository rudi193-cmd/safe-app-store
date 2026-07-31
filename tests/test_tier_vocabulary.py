"""Doc-vocabulary gate for the store refit's P0 (docs/store_refit_plan.md).

`CLAUDE.md` and `stores/README.md` used to name the lower tier differently —
"the shared playground" in one, "Stored" in the other — and put it in
different places, which is exactly why `stores/*/stored/` sat empty: nothing
downstream could be built honestly against a tier with two names. P0 settles
this by making both files use one vocabulary and state the same resolution:
`stores/{major}/stored/` holds a keeping *record*, never a second copy of the
build (the code stays in `apps/`).

This test is the gate that stops the collision reopening. It fails if either
file:
  - still calls the lower tier "Stored" (the old, competing tier name), or
  - uses the bare word "stored/" anywhere except as part of a full
    `stores/{major}/stored/` path — i.e. always a location marker for the
    keeping record, never prose implying the code itself sits there, or
  - drops the shared resolution sentence the two files are meant to agree on
    verbatim (whitespace-insensitive, since Markdown soft-wraps it).

Stdlib only.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

CLAUDE_MD = REPO / "CLAUDE.md"
STORES_README = REPO / "stores" / "README.md"

CANONICAL_SENTENCE = (
    "The code is not duplicated. The record is what `stores/` stores."
)

_MAJORS = ("python", "node", "rust", "go", "cpp", "obsidian")
_FULL_STORED_PATH = re.compile(
    r"stores/(?:\{major\}|" + "|".join(_MAJORS) + r")/stored/"
)
_BARE_STORED = re.compile(r"stored/")


def _normalise(text: str) -> str:
    """Collapse all whitespace so a sentence Markdown soft-wraps across lines
    still matches as one contiguous string."""
    return " ".join(text.split())


def _bare_stored_offenders(text: str) -> list[str]:
    covered_ends = {m.end() for m in _FULL_STORED_PATH.finditer(text)}
    offenders = []
    for m in _BARE_STORED.finditer(text):
        if m.end() not in covered_ends:
            line_no = text.count("\n", 0, m.start()) + 1
            offenders.append(f"line {line_no}: ...{text[max(0, m.start()-30):m.end()+10]!r}...")
    return offenders


def test_neither_doc_calls_the_lower_tier_stored():
    for path in (CLAUDE_MD, STORES_README):
        text = path.read_text(encoding="utf-8")
        assert "**Stored**" not in text, (
            f"{path.relative_to(REPO)} still names the lower tier 'Stored' — "
            "P0 renames it to 'playground' to match CLAUDE.md, so the two "
            "docs stop disagreeing about the same tier."
        )


def test_stored_only_ever_appears_as_a_full_store_path():
    for path in (CLAUDE_MD, STORES_README):
        text = path.read_text(encoding="utf-8")
        offenders = _bare_stored_offenders(text)
        assert not offenders, (
            f"{path.relative_to(REPO)} uses 'stored/' outside a full "
            f"stores/{{major}}/stored/ path, which reads as a code location "
            "rather than a keeping-record location:\n  " + "\n  ".join(offenders)
        )


def test_both_docs_state_the_same_resolution_sentence():
    for path in (CLAUDE_MD, STORES_README):
        text = _normalise(path.read_text(encoding="utf-8"))
        assert CANONICAL_SENTENCE in text, (
            f"{path.relative_to(REPO)} is missing the shared resolution "
            f"sentence ({CANONICAL_SENTENCE!r}) — P0 requires both files to "
            "state it verbatim so the law and the map agree."
        )


def test_both_docs_use_playground_as_the_tier_name():
    for path in (CLAUDE_MD, STORES_README):
        text = path.read_text(encoding="utf-8")
        assert "playground" in text.lower(), (
            f"{path.relative_to(REPO)} never uses 'playground' for the lower "
            "tier — the canonical name both docs must share."
        )
