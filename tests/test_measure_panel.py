"""Tests for stores/measure_panel.py — The Forge's measuring panel (the box's
lesson made mechanical: docs/design/the-forge-measure.md).

The panel runs a set of measuring INSTRUMENTS across a build, treats
CONVERGENCE (>=2 instruments naming the same artifact) as the alarm, and
reports its OWN coverage honestly (which instruments ran, which couldn't, and
what that blinds it to) — because a green harness on a rotten artifact is the
trap sigmap's 100/100-health-D-coverage split warns about.

Pure — the framework + the two dependency-free instruments (census, hygiene)
need no Nestor/fsrs/fleet tools; routing loads checkpoint_governance (soil +
human_loop, also pure). Written test-first.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location("measure_panel", _REPO / "stores" / "measure_panel.py")
measure_panel = importlib.util.module_from_spec(_spec)
sys.modules["measure_panel"] = measure_panel
_spec.loader.exec_module(measure_panel)

Finding = measure_panel.Finding
BUILDER_A = "a" * 32


def _box(tmp_path) -> Path:
    """A miniature of the exhibit: tiny real code + one dominating committed
    log — the shape all four box instruments converged on."""
    d = tmp_path / "build"
    (d / "src").mkdir(parents=True)
    (d / "src" / "app.py").write_text("def main():\n    return 1\n")
    (d / "src" / "util.py").write_text("def helper():\n    return 2\n")
    (d / "error_log").write_text("scan wp-login.php\n" * 20000)  # the 93%-of-the-repo file
    return d


# ── the census instrument (size share — the error_log class) ─────────────────

def test_census_flags_a_file_that_dominates_the_repo(tmp_path):
    d = _box(tmp_path)
    findings = measure_panel.CensusInstrument().measure(d)
    hot = [f for f in findings if "error_log" in f.artifact]
    assert hot, "census should flag the dominating log"
    assert hot[0].instrument == "census"


def test_census_says_nothing_about_a_balanced_tree(tmp_path):
    d = tmp_path / "build"
    (d).mkdir()
    (d / "a.py").write_text("x = 1\n" * 50)
    (d / "b.py").write_text("y = 2\n" * 50)
    assert measure_panel.CensusInstrument().measure(d) == []


# ── the hygiene instrument (committed-by-accident smells) ────────────────────

def test_hygiene_flags_a_log_and_a_backup(tmp_path):
    d = tmp_path / "build"
    d.mkdir()
    (d / "error_log").write_text("x\n")
    (d / "db.bak").write_text("x\n")
    (d / "app.py").write_text("ok = 1\n")
    flagged = {Path(f.artifact).name for f in measure_panel.HygieneInstrument().measure(d)}
    assert "error_log" in flagged
    assert "db.bak" in flagged
    assert "app.py" not in flagged


# ── convergence: the alarm ───────────────────────────────────────────────────

def test_two_instruments_naming_the_same_artifact_converge(tmp_path):
    d = _box(tmp_path)
    report = measure_panel.run_panel(d, [measure_panel.CensusInstrument(), measure_panel.HygieneInstrument()])
    # census (biggest) and hygiene (it's a log) both name error_log -> convergent
    conv = [c for c in report.convergent if "error_log" in c.artifact]
    assert conv, "error_log should be a convergent finding (>=2 instruments)"
    assert set(conv[0].instruments) >= {"census", "hygiene"}


def test_a_single_instrument_finding_is_not_convergence(tmp_path):
    # only hygiene flags a small stray .bak; census ignores it (not dominant)
    d = tmp_path / "build"
    d.mkdir()
    (d / "app.py").write_text("x = 1\n" * 100)
    (d / "notes.bak").write_text("tiny\n")
    report = measure_panel.run_panel(d, [measure_panel.CensusInstrument(), measure_panel.HygieneInstrument()])
    assert report.convergent == []          # one witness is not the alarm
    assert any("notes.bak" in f.artifact for f in report.findings)  # still recorded


def test_convergence_frame_is_instrument_agnostic():
    """The convergence logic itself, tested with fake instruments that return
    known findings — independent of census/hygiene specifics."""
    class _Fake(measure_panel.Instrument):
        def __init__(self, name, arts):
            self._n, self._a = name, arts
        @property
        def name(self):
            return self._n
        def measure(self, build_dir):
            return [Finding(instrument=self._n, artifact=a, metric="m", value=1, severity="med", detail="") for a in self._a]

    report = measure_panel.run_panel(
        Path("/nonexistent"),
        [_Fake("i1", ["x.py", "y.py"]), _Fake("i2", ["y.py", "z.py"]), _Fake("i3", ["y.py"])],
    )
    conv = {c.artifact: set(c.instruments) for c in report.convergent}
    assert conv == {"y.py": {"i1", "i2", "i3"}}   # only y.py named by >=2


# ── honest coverage (the sigmap health-vs-coverage lesson) ───────────────────

def test_report_names_the_instruments_that_ran(tmp_path):
    d = _box(tmp_path)
    report = measure_panel.run_panel(d, [measure_panel.CensusInstrument(), measure_panel.HygieneInstrument()])
    assert set(report.ran) == {"census", "hygiene"}
    # even a run WITH findings states what it did NOT look at — by name, with
    # the fleet tool for each (the sigmap health-vs-coverage lesson)
    note = report.coverage_note()
    assert "census" in note and "hygiene" in note
    assert "call-graph" in note and "codebase-memory" in note   # named as uncovered
    assert "execution" in note and "kartikeya" in note
    covered = {cls for cls, _ in report.not_covered}
    assert {"call-graph", "execution", "calibration"} <= covered  # not run this bite


def test_an_unavailable_instrument_is_a_coverage_gap_not_a_crash(tmp_path):
    class _Down(measure_panel.Instrument):
        name = "call-graph"
        def measure(self, build_dir):
            raise measure_panel.InstrumentUnavailable("codebase-memory binary not installed")

    d = _box(tmp_path)
    report = measure_panel.run_panel(d, [measure_panel.CensusInstrument(), _Down()])
    assert "census" in report.ran
    assert any(name == "call-graph" for name, _ in report.unavailable)
    # the gap is stated in the coverage note (harness honest about what it can't see)
    assert "call-graph" in report.coverage_note()


# ── routing convergent findings into the human_loop queue (reuse) ────────────

def test_convergent_findings_route_to_the_governance_queue_deduped(tmp_path):
    root = tmp_path / "checkpoints"
    d = _box(tmp_path)
    report = measure_panel.run_panel(d, [measure_panel.CensusInstrument(), measure_panel.HygieneInstrument()])
    n = measure_panel.route(report, builder_id=BUILDER_A, root=root)
    assert n >= 1
    gov = measure_panel.checkpoint_governance
    items = gov.open_items(BUILDER_A, root=root)
    assert any("error_log" in it["title"] or "error_log" in it.get("summary", "") for it in items)
    # routing again does not pile up duplicates (source_ref dedup)
    measure_panel.route(report, builder_id=BUILDER_A, root=root)
    assert len(gov.open_items(BUILDER_A, root=root)) == len(items)
