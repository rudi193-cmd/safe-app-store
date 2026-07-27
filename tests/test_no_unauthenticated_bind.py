"""Drift-guard: no app hardcodes a bind to all interfaces (box audit B9).

Two apps served their full API on ``host="0.0.0.0"`` with CORS but no auth — and
CORS is a *browser* control, so a direct (non-browser) request from anywhere on
the segment reached the whole API. These are local-first apps; the bind now
defaults to loopback and takes an env override for an operator who deliberately
wants a wider bind (and adds their own auth/proxy).

This test fails if any live (non-archived, non-test) app file hardcodes a
``0.0.0.0`` bind again. A wide bind must come from configuration
(``host=os.environ.get(...)``), never a literal — so the exposure can't be
reintroduced by a one-line default.
"""
import re
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent

# A bind argument set to the all-interfaces literal: host="0.0.0.0" /
# host='0.0.0.0' (any whitespace). Matches the *bind*, not a mention in prose —
# a comment like "a 0.0.0.0 bind" has no ``host=`` prefix.
_HARDCODED_BIND = re.compile(r"""host\s*=\s*["']0\.0\.0\.0["']""")

_SKIP_PARTS = {"_archived", "__pycache__", ".git", "node_modules", ".venv",
               "venv", "tests", "test"}


def _live_app_py_files():
    for p in (_REPO / "apps").rglob("*.py"):
        if _SKIP_PARTS & set(p.parts):
            continue
        yield p


def test_no_app_hardcodes_all_interfaces_bind():
    offenders = []
    for p in _live_app_py_files():
        text = p.read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(text.splitlines(), 1):
            if _HARDCODED_BIND.search(line):
                offenders.append(f"{p.relative_to(_REPO)}:{i}  {line.strip()}")
    assert not offenders, (
        "hardcoded all-interfaces bind reintroduced (box audit B9) — default to "
        "127.0.0.1 and take a wider bind from an env override (and add auth) "
        "instead:\n  " + "\n  ".join(sorted(offenders)))
