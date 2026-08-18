"""The shared egress subject-id guard, swept exhaustively in one place.

`_egress.validate_subject` is the one validator both export paths (the school form
and the emergency card) call before anything is served or written — the answer to
the bites 2–5 audit's critical finding, and to its root lesson: *do not keep two
validators for the same rule.* Because both paths ride on this one function, its
adversarial coverage lives here, once, rather than being partly re-swept in each
export's own test (the H-3 audit noted the emergency card's own test exercised only
a single bad id). If this passes, both egress paths are covered by construction.
"""
from __future__ import annotations

import pytest

from homestead.keep.export import ExportRefused

from homestead_health._egress import validate_subject

# Every id here must be refused *before* any export writes — the newline is the
# audit's exact leak (keep/export accepts it, keep/logs rejects it, and the write
# lands between the two), and the rest are the family it belongs to: separators,
# path escapes, control characters, and the whitespace `str.isspace()` sees plus the
# zero-width and bidi characters it does not.
BAD = [
    "subj-01\nFORGED",      # newline — the audit's canonical leak
    "subj-01\r\nFORGED",    # CRLF
    "a\tb",                 # tab
    "a\x00b",               # NUL
    "a\x0bb",               # vertical tab (a control char)
    "a\x85b",               # NEL, a Unicode control (Cc)
    "a\u2028b",             # line separator (isspace True, category Zl)
    "a\u2029b",             # paragraph separator (Zp)
    "a\u200bb",             # zero-width space — isspace() is False for it (Cf)
    "a\ufeffb",             # BOM / zero-width no-break space (Cf)
    "a\u202eb",             # right-to-left override (Cf)
    "a/b",                  # path separator
    "a\\b",                 # backslash
    ".",                    # a dot segment
    "..",                   # a parent-dir escape
    "   ",                  # whitespace only
    "",                     # empty
    None,                   # not a subject at all
]

# These are unusual but legitimate — a dot inside a name, not a segment — and must
# pass, so the guard refuses malice without refusing every odd-looking real id.
GOOD = ["subj-01", "subj-07", "a..b", "sub.ject", "a-b_c", "SUBJ01"]


@pytest.mark.parametrize("bad", BAD)
def test_a_malformed_subject_is_refused(bad):
    with pytest.raises(ExportRefused):
        validate_subject(bad)


@pytest.mark.parametrize("good", GOOD)
def test_a_clean_subject_id_passes(good):
    assert validate_subject(good) == good


def test_both_export_paths_call_this_one_validator():
    """The refactor's whole point: one validator, so the two cannot drift. Both
    modules import `validate_subject` from `_egress`, so a fix or a tightening here
    reaches the school form and the emergency card at once — the failure mode
    (two validators for one rule) that caused the engine bug this answers."""
    import homestead_health.emergency as emergency
    import homestead_health.school_form as school_form

    assert emergency.validate_subject is validate_subject
    assert school_form.validate_subject is validate_subject
