"""Drift-guard for box-audit B3 — no app reads the shared SOIL store raw.

The finding: ~8 hosted apps ran ``SELECT data FROM records WHERE deleted=0 AND
data LIKE ?`` directly against the shared ``knowledge`` store — the whole table,
no per-app scope (the records schema has no scope column), so any app's
``query("password")`` returned every other app's atoms, bypassing the gate. KB
reads must go through the gated ``knowledge_search`` tool instead.

This test fails if any live (non-archived) app file reintroduces that raw read,
so the class of bug can't creep back the way it spread the first time.
"""
import re
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
# The unscoped raw read: a SELECT from `records` filtered only by a content LIKE
# (no collection / app scope). Deliberately broad on whitespace.
_RAW_READ = re.compile(r"FROM\s+records\b(?:(?!collection|app_id).)*?data\s+LIKE",
                       re.IGNORECASE | re.DOTALL)


def _live_app_py_files():
    for p in (_REPO / "apps").rglob("*.py"):
        if "_archived" in p.parts or "__pycache__" in p.parts:
            continue
        yield p


def test_no_app_reads_the_shared_soil_store_raw():
    offenders = []
    for p in _live_app_py_files():
        text = p.read_text(encoding="utf-8", errors="replace")
        # (1) The SOIL `records` shape: a content LIKE with no app scope.
        for m in re.finditer(r"FROM\s+records\b.{0,200}", text, re.IGNORECASE | re.DOTALL):
            snippet = m.group(0)
            if re.search(r"data\s+LIKE", snippet, re.IGNORECASE) and \
               not re.search(r"\bcollection\b|\bapp_id\b", snippet, re.IGNORECASE):
                offenders.append(str(p.relative_to(_REPO)))
                break
        else:
            # (2) The shared KB table directly: any app reading `willow.knowledge`
            # bypasses the gate (there's no app-scope column) — the-binder's old
            # postgres fallback, box audit B3-residual. knowledge_search only.
            if re.search(r"FROM\s+willow\.knowledge\b", text, re.IGNORECASE):
                offenders.append(str(p.relative_to(_REPO)))
    assert not offenders, (
        "raw unscoped shared-KB reads reintroduced (box audit B3) — route through "
        "the gated knowledge_search tool instead:\n  " + "\n  ".join(sorted(offenders)))
