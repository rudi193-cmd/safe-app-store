"""Tests for stores/instrument_callgraph.py — the panel's first real fleet
instrument (codebase-memory-mcp call graph, docs/design/the-forge-measure.md).

The dead-code SET DIFFERENCE is a pure function, tested against captured
codebase-memory output (no binary needed). The real end-to-end drive is
`skipif`'d when the binary isn't runnable (as bite 0 skips when bwrap is
absent). The unavailable-path is always tested.
"""
from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location(
    "instrument_callgraph", _REPO / "stores" / "instrument_callgraph.py"
)
icg = importlib.util.module_from_spec(_spec)
sys.modules["instrument_callgraph"] = icg
_spec.loader.exec_module(icg)


# ── the pure dead-code core (captured output, no binary) ─────────────────────

# Real query results captured from codebase-memory-mcp 0.10.0 on a 3-function
# project (used<-main, dead_function uncalled, main entry-point).
_ALL = """rows: 5  (cols: qn entry file)
  tmp-cbm-probe.app.used "false" app.py
  tmp-cbm-probe.app.dead_function "false" app.py
  tmp-cbm-probe.app.main "true" app.py
  builtins.len "false" <python-builtins>
  builtins.print "false" <python-builtins>
total: 5"""

_CALLED = """rows: 1  (cols: qn)
  tmp-cbm-probe.app.used
total: 1"""


def test_dead_functions_is_the_set_difference():
    dead = icg._dead_functions(_ALL, _CALLED)
    assert dead == [("tmp-cbm-probe.app.dead_function", "app.py")]
    # used is called; main is an entry point; builtins excluded — none dead
    qns = {qn for qn, _ in dead}
    assert "tmp-cbm-probe.app.used" not in qns
    assert "tmp-cbm-probe.app.main" not in qns
    assert not any(f.startswith("<") for _, f in dead)


def test_dead_functions_handles_a_file_path_with_spaces():
    all_text = 'rows: 1  (cols: qn entry file)\n  pkg.mod.orphan "false" src/my dir/x.py\ntotal: 1'
    dead = icg._dead_functions(all_text, "rows: 0\ntotal: 0")
    assert dead == [("pkg.mod.orphan", "src/my dir/x.py")]  # file kept intact


def test_empty_results_yield_no_dead():
    assert icg._dead_functions("rows: 0\ntotal: 0", "rows: 0\ntotal: 0") == []


# ── unavailable path (always runs) ───────────────────────────────────────────

def test_missing_binary_is_instrument_unavailable(tmp_path):
    inst = icg.CallGraphInstrument(binary="/no/such/codebase-memory-mcp-binary")
    with pytest.raises(icg.InstrumentUnavailable):
        inst.measure(tmp_path)


# ── real end-to-end drive (skipped if the binary can't run) ──────────────────

def _binary():
    exe = shutil.which("codebase-memory-mcp") or "/tmp/forge-audit-venv/bin/codebase-memory-mcp"
    if not Path(exe).exists():
        return None
    try:
        subprocess.run([exe, "--version"], capture_output=True, timeout=30)
    except Exception:
        return None
    return exe


_BIN = _binary()


@pytest.mark.skipif(_BIN is None, reason="codebase-memory-mcp binary not runnable in this environment")
def test_drives_the_real_tool_and_flags_dead_code(tmp_path):
    d = tmp_path / "proj"
    d.mkdir()
    (d / "app.py").write_text(
        "def used():\n    return 1\n\n"
        "def dead_function():\n    return 2\n\n"
        "def main():\n    return used()\n"
    )
    findings = icg.CallGraphInstrument(binary=_BIN).measure(d)
    files_flagged = {f.artifact for f in findings}
    dead_detail = " ".join(f.detail for f in findings)
    assert any("app.py" in a for a in files_flagged), findings
    assert "dead_function" in dead_detail
    assert all(f.metric == "fan_in" and f.value == 0 for f in findings)


@pytest.mark.skipif(_BIN is None, reason="codebase-memory-mcp binary not runnable in this environment")
def test_a_fully_wired_program_has_no_dead_code(tmp_path):
    d = tmp_path / "proj"
    d.mkdir()
    (d / "app.py").write_text(
        "def a():\n    return 1\n\n"
        "def b():\n    return a()\n\n"
        "def main():\n    return b()\n"
    )
    # a<-b<-main, main is entry -> nothing is dead
    findings = icg.CallGraphInstrument(binary=_BIN).measure(d)
    assert findings == [], findings
