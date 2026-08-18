"""Shared guards for the module's export paths — one validator, so two cannot drift.

The bites 2–5 audit's critical finding (C1) was an engine defect *of exactly this
shape*: two independently-written reference-component validators (`keep/export`'s
and `keep/logs`') disagreed about a newline, and an export wrote the artifact and
committed the ledger before the stricter one refused it — a leak that looked like a
refusal. The lesson is not only "validate before writing"; it is "do not keep two
validators for the same rule." Every export this module grows — the school form, the
emergency card, whatever follows — validates its subject id the same way, from here,
so the fix is applied to all of them by construction and none can drift from another.
"""
from __future__ import annotations

import unicodedata

from homestead.keep.export import ExportRefused

__all__ = ["validate_subject"]


def validate_subject(subject: object) -> str:
    """The subject id, validated as one clean reference segment — before any write.

    A subject id becomes a path segment (the artifact tree) **and** a log reference,
    and the engine holds those to two validators that do not agree on every
    character (`keep/export._segment` accepts an embedded newline, `keep/logs._ref`
    rejects it). Because `export_record` writes the artifact and commits the
    `IntegrityLog` entry *before* it touches the `VisibleLog`, an id with a newline
    would leave the record on disk and in the ledger and then raise when the visible
    log refused it — a leak that looks like a refusal.

    So the id is validated at the app boundary, before a single datum is served or
    written: no separator, no `..`, and no control, format, or whitespace character
    of any kind (a newline, a tab, a zero-width space — `str.isspace()` misses the
    last, so the Unicode category is checked too). A malformed subject fails closed,
    with nothing written. `None` is refused rather than stringified to the
    collision-prone literal `"None"`.
    """
    if subject is None:
        raise ExportRefused("an export names a subject; got None")
    sid = str(subject)
    if not sid.strip():
        raise ExportRefused("an export names a subject; got an empty reference")
    if sid in (".", ".."):
        raise ExportRefused(f"subject {sid!r} is not a usable reference segment")
    for ch in sid:
        if ch in "/\\" or ch == "\x00" or ch.isspace() or unicodedata.category(ch)[0] == "C":
            raise ExportRefused(
                f"subject {sid!r} carries a separator, control, format, or "
                "whitespace character — a reference component must be one clean "
                "segment, or the export writes before the visible log refuses it"
            )
    return sid
