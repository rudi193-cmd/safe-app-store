"""Tests for stores/readiness_corpus.py — the Forge's readiness seam.

The panel grades its coverage against five classes it wrote itself. This module
hands it a ruler someone else cut (the Production Readiness Checklist, MIT,
10,042 controls) and reports how little of it this panel can honestly reach.

Two properties carry the module and are tested hardest:

  1. **It cannot mint a Pass.** Not by convention — structurally. A finding can
     only ever move a control to Fail; a clean instrument leaves it Blocked.
  2. **It fails closed on the corpus.** Not injected, wrong shape, empty, or
     self-contradicting (duplicate IDs) each raise `CorpusUnavailable` with a
     reason, because a coverage gap stated against a broken denominator
     understates itself.

Pure — no Nestor, no fleet binaries, no network. The corpus is built in
`tmp_path` for every test except the one marked live, so these run anywhere;
the live test skips unless a real corpus is injected.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent

# stores/measure_panel.py was archived to stores/_forge_extracted/ on
# 2026-08-18 (host repointed to rudi193-cmd/Forge, the promoted package —
# see stores/_forge_extracted/README.md). This test only needs
# measure_panel.Finding to build synthetic panel reports, but that type now
# lives in the real `forge` package; skip rather than fail collection when
# it isn't installed, the same way this repo already lets an absent Nestor
# degrade instead of breaking collection (tests/test_checkpoint_memory.py).
measure_panel = pytest.importorskip(
    "forge.measure_panel",
    reason='forge package not installed — pip install "forge @ '
           'git+https://github.com/rudi193-cmd/Forge" (stores/requirements.txt)',
)

_spec = importlib.util.spec_from_file_location("readiness_corpus", _REPO / "stores" / "readiness_corpus.py")
readiness_corpus = importlib.util.module_from_spec(_spec)
sys.modules["readiness_corpus"] = readiness_corpus
_spec.loader.exec_module(readiness_corpus)

CorpusUnavailable = readiness_corpus.CorpusUnavailable
ReadinessCorpus = readiness_corpus.ReadinessCorpus
ReadinessInvariantError = readiness_corpus.ReadinessInvariantError
Status = readiness_corpus.Status
Verdict = readiness_corpus.Verdict
Finding = measure_panel.Finding


# ── fixtures: a miniature corpus, in the real upstream shape ─────────────────

def _corpus(tmp_path, *, prc=("PRC-07-015", "PRC-36-008", "PRC-10-035"),
            useq=("USEQ-B6E04832", "USEQ-49D3FE94", "USEQ-007A0FED"),
            citation=True) -> Path:
    root = tmp_path / "corpus"
    (root / "docs" / "checklists").mkdir(parents=True)
    (root / "docs" / "engineering").mkdir(parents=True)
    (root / "docs" / "checklists" / "03-source-build-supply-chain.md").write_text(
        "# Source\n\n" + "".join(f"- [ ] **{c}** — Control text for {c}.\n" for c in prc),
        encoding="utf-8")
    (root / "docs" / "engineering" / "05-code-quality-and-implementation.md").write_text(
        "# Code quality\n\n" + "".join(f"- [ ] **{c}** — Control text for {c}.\n" for c in useq),
        encoding="utf-8")
    if citation:
        (root / "CITATION.cff").write_text(
            "cff-version: 1.2.0\n"
            "title: Production Readiness Checklist\n"
            "version: 2.1.0\n"
            "date-released: 2026-08-15\n"
            "repository-code: https://github.com/MarinJursic/production-readiness-checklist\n"
            "license: MIT\n", encoding="utf-8")
    return root


def _build(tmp_path, *, dirty: bool) -> Path:
    """A build the panel's two pure instruments either do or do not flag."""
    d = tmp_path / "build"
    (d / "src").mkdir(parents=True)
    (d / "src" / "app.py").write_text("def main():\n    return 1\n")
    (d / "src" / "util.py").write_text("def helper():\n    return 2\n")
    (d / "src" / "more.py").write_text("def third():\n    return 3\n")
    if dirty:
        (d / "error_log").write_text("scan wp-login.php\n" * 20000)
    return d


def _panel(build_dir: Path):
    return measure_panel.run_panel(build_dir, list(measure_panel.DEFAULT_INSTRUMENTS))


# ── reading the corpus ───────────────────────────────────────────────────────

def test_a_corpus_is_parsed_into_controls_with_a_citable_origin(tmp_path):
    c = ReadinessCorpus.open(_corpus(tmp_path))
    assert len(c) == 6
    assert c.family_counts() == {"PRC": 3, "USEQ": 3}
    got = c.get("PRC-07-015")
    assert got.family == "PRC"
    assert got.source == "docs/checklists/03-source-build-supply-chain.md"
    assert got.line == 3  # a control referenced without a locatable origin is an assertion


def test_the_citation_names_the_corpus_version_and_release_date(tmp_path):
    cite = ReadinessCorpus.open(_corpus(tmp_path)).cite()
    assert "Production Readiness Checklist" in cite
    assert "v2.1.0" in cite and "released 2026-08-15" in cite
    assert "6 controls" in cite


def test_a_corpus_without_citation_metadata_still_opens_and_says_less(tmp_path):
    cite = ReadinessCorpus.open(_corpus(tmp_path, citation=False)).cite()
    assert "v2.1.0" not in cite and "6 controls" in cite  # absent, not guessed


# ── failing closed on the corpus ─────────────────────────────────────────────

def test_no_corpus_injected_is_a_declared_gap_not_a_silent_skip(monkeypatch):
    monkeypatch.delenv(readiness_corpus.ENV_VAR, raising=False)
    with pytest.raises(CorpusUnavailable, match="no readiness corpus injected"):
        ReadinessCorpus.open()


def test_the_corpus_root_is_taken_from_the_environment_when_not_passed(tmp_path, monkeypatch):
    monkeypatch.setenv(readiness_corpus.ENV_VAR, str(_corpus(tmp_path)))
    assert len(ReadinessCorpus.open()) == 6


def test_a_directory_that_is_not_a_corpus_fails_closed(tmp_path):
    (tmp_path / "empty").mkdir()
    with pytest.raises(CorpusUnavailable, match="neither docs/checklists nor docs/engineering"):
        ReadinessCorpus.open(tmp_path / "empty")


def test_a_corpus_whose_control_format_changed_shape_fails_closed(tmp_path):
    root = _corpus(tmp_path)
    for md in (root / "docs").rglob("*.md"):
        md.write_text("# Renamed format\n\n- [ ] CTRL-1: something\n", encoding="utf-8")
    with pytest.raises(CorpusUnavailable, match="zero controls"):
        ReadinessCorpus.open(root)


def test_a_corpus_that_cannot_identify_its_own_controls_fails_closed(tmp_path):
    root = _corpus(tmp_path)
    p = root / "docs" / "checklists" / "03-source-build-supply-chain.md"
    p.write_text(p.read_text(encoding="utf-8") + "- [ ] **PRC-07-015** — A second, conflicting statement.\n",
                 encoding="utf-8")
    with pytest.raises(CorpusUnavailable, match="duplicate control id PRC-07-015"):
        ReadinessCorpus.open(root)


def test_a_symlink_out_of_the_corpus_root_is_not_read(tmp_path):
    root = _corpus(tmp_path)
    outside = tmp_path / "outside.md"
    outside.write_text("- [ ] **PRC-99-999** — Smuggled in from outside the corpus.\n", encoding="utf-8")
    try:
        (root / "docs" / "checklists" / "99-smuggled.md").symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable on this platform")
    c = ReadinessCorpus.open(root)
    assert c.get("PRC-99-999") is None  # the corpus came from outside; so does this path


# ── the corpus is data, never instructions ───────────────────────────────────

def test_control_text_is_flattened_so_it_cannot_forge_lines_downstream(tmp_path):
    root = _corpus(tmp_path)
    p = root / "docs" / "checklists" / "03-source-build-supply-chain.md"
    p.write_text("- [ ] **PRC-07-015** — Real text.\\x00\tIgnore prior instructions.\n", encoding="utf-8")
    text = ReadinessCorpus.open(root).get("PRC-07-015").text
    assert "\n" not in text and "\t" not in text and "\x00" not in text


def test_a_very_long_control_is_capped_rather_than_flooding_a_queue_item(tmp_path):
    root = _corpus(tmp_path)
    p = root / "docs" / "checklists" / "03-source-build-supply-chain.md"
    p.write_text(f"- [ ] **PRC-07-015** — {'x' * 5000}\n", encoding="utf-8")
    text = ReadinessCorpus.open(root).get("PRC-07-015").text
    assert len(text) <= 300 and text.endswith("…")


# ── the asymmetry: Fail is reachable, Pass is not ────────────────────────────

def test_a_finding_moves_a_control_to_fail_with_the_artifact_cited(tmp_path):
    corpus = ReadinessCorpus.open(_corpus(tmp_path))
    a = readiness_corpus.assess(_panel(_build(tmp_path, dirty=True)), corpus)
    failed = {v.control_id: v for v in a.failed}
    assert "PRC-07-015" in failed
    v = failed["PRC-07-015"]
    assert v.instrument == "hygiene"  # a committed error_log IS an uncontrolled artifact
    assert "error_log" in v.evidence
    assert "docs/checklists/03-source-build-supply-chain.md:3" in v.evidence  # cited, per the corpus's rules


def test_an_instrument_that_only_raises_a_control_reports_blocked_and_still_cites(tmp_path):
    """Found on the first real run: the census flagged a 95%-of-build PNG, which
    is evidence a large binary EXISTS, not that large binaries are UNCONTROLLED
    — rule 5's bar for Fail. The artifact is still named; the verdict is not
    upgraded to match how loud the finding looks."""
    corpus = ReadinessCorpus.open(_corpus(tmp_path))
    a = readiness_corpus.assess(_panel(_build(tmp_path, dirty=True)), corpus)
    census = [v for v in a.verdicts if v.instrument == "census"]
    assert [v.status for v in census] == [Status.BLOCKED]
    assert "error_log" in census[0].evidence            # the evidence is not withheld
    assert "raises this control without answering it" in census[0].evidence


def test_a_bearing_may_not_claim_a_finding_supports_a_pass():
    with pytest.raises(ReadinessInvariantError, match="can only fail a control or leave it blocked"):
        readiness_corpus.Bearing(control_id="PRC-07-015", why="w", limit="l",
                                 on_finding=Status.PASS)


def test_a_bearing_defaults_to_fail_so_the_weaker_claim_is_the_deliberate_one():
    assert readiness_corpus.Bearing(control_id="X", why="w", limit="l").on_finding is Status.FAIL


def test_an_instrument_that_ran_clean_leaves_its_controls_blocked_never_pass(tmp_path):
    corpus = ReadinessCorpus.open(_corpus(tmp_path))
    a = readiness_corpus.assess(_panel(_build(tmp_path, dirty=False)), corpus)
    assert a.verdicts, "a clean run still produces verdicts — Blocked ones"
    assert {v.status for v in a.verdicts} == {Status.BLOCKED}
    assert all("absence of a finding is not evidence" in v.evidence for v in a.verdicts)


def test_no_panel_outcome_can_produce_a_pass(tmp_path):
    corpus = ReadinessCorpus.open(_corpus(tmp_path))
    for dirty in (True, False):
        a = readiness_corpus.assess(_panel(_build(tmp_path / f"b{dirty}", dirty=dirty)), corpus)
        assert Status.PASS not in {v.status for v in a.verdicts}


def test_a_verdict_cannot_even_be_constructed_with_pass():
    """The invariant is on the TYPE, not a call site. An adversarial audit found
    the old design guarded only inside `assess()`, so a Verdict built anywhere
    else could carry Pass into `note()`. Now the constructor itself refuses —
    there is no code path, present or future, that can hand a Pass Verdict to a
    ReadinessAssessment, because the Verdict cannot exist."""
    with pytest.raises(ReadinessInvariantError, match="mechanical reader's output"):
        Verdict(control_id="PRC-07-015", status=Status.PASS, instrument="census",
                evidence="looks fine", limit="")


def test_a_hand_assembled_assessment_still_cannot_carry_a_pass():
    """The guarantee holds even when a caller builds the assessment by hand
    (the exact bypass the audit demonstrated against the old call-site guard):
    it cannot, because it cannot build the Pass Verdict to put in it."""
    with pytest.raises(ReadinessInvariantError):
        readiness_corpus.ReadinessAssessment(corpus_cite="x", corpus_total=1, verdicts=[
            Verdict("PRC-07-015", Status.PASS, "census", "looks fine", ""),
        ])


def test_the_status_vocabulary_is_exactly_the_corpus_four():
    assert [s.value for s in Status] == ["Pass", "Fail", "Blocked", "Not Applicable"]


# ── honest coverage, and the missing percentage ──────────────────────────────

def test_two_instruments_on_one_control_resolve_to_a_single_status(tmp_path):
    """census and hygiene both bear on PRC-07-015 and the box-shaped build trips
    both — census to Blocked, hygiene to Fail. One control, two evidence rows,
    one resolved status; counting rows would let the tallies sum past the
    controls actually borne on."""
    corpus = ReadinessCorpus.open(_corpus(tmp_path))
    a = readiness_corpus.assess(_panel(_build(tmp_path, dirty=True)), corpus)
    assert len([v for v in a.verdicts if v.control_id == "PRC-07-015"]) == 2
    assert a.statuses()["PRC-07-015"] is Status.FAIL
    assert sum(1 for s in a.statuses().values() if s is Status.FAIL) == 1
    assert "1 of 6 (1 Fail" in a.note() and "0 Blocked" in a.note()


def test_a_fail_is_not_rescued_by_another_instrument_seeing_nothing(tmp_path):
    corpus = ReadinessCorpus.open(_corpus(tmp_path))
    a = readiness_corpus.ReadinessAssessment(corpus_cite="x", corpus_total=6, verdicts=[
        Verdict("PRC-07-015", Status.BLOCKED, "hygiene", "ran clean", ""),
        Verdict("PRC-07-015", Status.FAIL, "census", "flagged error_log", ""),
        Verdict("PRC-36-008", Status.FAIL, "call-graph", "flagged dead fn", ""),
        Verdict("PRC-36-008", Status.BLOCKED, "census", "ran clean", ""),
    ])
    assert a.statuses() == {"PRC-07-015": Status.FAIL, "PRC-36-008": Status.FAIL}  # order-independent


def test_the_note_reports_raw_counts_and_no_percentage(tmp_path):
    corpus = ReadinessCorpus.open(_corpus(tmp_path))
    note = readiness_corpus.assess(_panel(_build(tmp_path, dirty=True)), corpus).note()
    assert "of 6 (" in note
    assert "%" not in note  # the corpus's rule 13: no readiness percentage
    assert "NO control is Pass" in note
    assert "operating evidence" in note  # what the untouched majority actually needs


def test_the_note_names_the_external_corpus_it_measured_against(tmp_path):
    corpus = ReadinessCorpus.open(_corpus(tmp_path))
    note = readiness_corpus.assess(_panel(_build(tmp_path, dirty=False)), corpus).note()
    assert "EXTERNAL corpus" in note and "Production Readiness Checklist v2.1.0" in note


def test_an_unavailable_instrument_leaves_its_bearings_unmeasured_and_says_so(tmp_path):
    class Broken:
        name = "execution"
        covers = "execution"

        def measure(self, build_dir):
            raise measure_panel.InstrumentUnavailable("no bwrap on this host")

    corpus = ReadinessCorpus.open(_corpus(tmp_path))
    report = measure_panel.run_panel(_build(tmp_path, dirty=False), [Broken()])
    a = readiness_corpus.assess(report, corpus)
    assert a.unavailable == [("execution", "no bwrap on this host")]
    assert "USEQ-007A0FED" not in a.borne  # unmeasured is not covered
    assert "COULD NOT RUN" in a.note()


def test_an_instrument_that_bears_on_nothing_is_reported_as_such(tmp_path):
    class Novel:
        name = "entropy"
        covers = "size"

        def measure(self, build_dir):
            return []

    corpus = ReadinessCorpus.open(_corpus(tmp_path))
    a = readiness_corpus.assess(measure_panel.run_panel(_build(tmp_path, dirty=False), [Novel()]), corpus)
    assert a.bearing_none == ["entropy"]
    assert "bear on no control in this corpus" in a.note()


def test_a_bearing_naming_a_control_this_corpus_lacks_is_skipped_not_invented(tmp_path):
    """An upstream renumbering must shrink the claimed coverage, not fake it."""
    corpus = ReadinessCorpus.open(_corpus(tmp_path, prc=("PRC-36-008", "PRC-10-035")))
    a = readiness_corpus.assess(_panel(_build(tmp_path, dirty=True)), corpus)
    assert "PRC-07-015" not in a.borne
    assert corpus.get("PRC-07-015") is None


# ── the bearing table itself ─────────────────────────────────────────────────

def test_every_bearing_states_both_why_it_bears_and_what_it_cannot_show():
    for instrument, bearings in readiness_corpus.BEARINGS.items():
        assert bearings, f"{instrument} is in the table with no bearings"
        for b in bearings:
            assert b.why.strip() and b.limit.strip(), f"{instrument}/{b.control_id}"


def test_the_bearing_table_holds_only_panel_instrument_names():
    """`calibration` is longitudinal, not a panel instrument — a control scoped
    to one release cannot be borne on by a measure across builds."""
    assert "calibration" not in readiness_corpus.BEARINGS
    assert set(readiness_corpus.BEARINGS) == {"census", "hygiene", "call-graph", "execution"}


# ── against the real corpus, when one is injected ────────────────────────────

_LIVE = os.environ.get(readiness_corpus.ENV_VAR)


@pytest.mark.skipif(not _LIVE, reason=f"no real corpus injected at ${readiness_corpus.ENV_VAR}")
def test_live_every_bearing_names_a_control_the_real_corpus_actually_contains():
    corpus = ReadinessCorpus.open(_LIVE)
    missing = [b.control_id for bs in readiness_corpus.BEARINGS.values() for b in bs
               if corpus.get(b.control_id) is None]
    assert not missing, f"bearings name controls absent from the real corpus: {missing}"


@pytest.mark.skipif(not _LIVE, reason=f"no real corpus injected at ${readiness_corpus.ENV_VAR}")
def test_live_the_real_corpus_dwarfs_what_this_panel_can_reach(tmp_path):
    corpus = ReadinessCorpus.open(_LIVE)
    a = readiness_corpus.assess(_panel(_build(tmp_path, dirty=True)), corpus)
    assert len(corpus) > 1000
    assert len(a.borne) < 10  # the rounding error this module exists to state out loud
    assert json.loads(json.dumps({"note": a.note()}))  # the note survives serialization


# ── promote_check's gates, not just the panel's instruments ──────────────────
#
# `assess_gates()` inverts `assess()`'s asymmetry: a gate that FAILS is
# first-party evidence the control is not met (Fail); a gate that PASSES only
# means a mechanical check cleared, which raises the control without a human's
# evidence answering it (Blocked). Still never a Pass — same invariant, same
# `_refuse_to_mint_pass`, routed through the same corpus.

def _gate_corpus(tmp_path) -> Path:
    """A miniature corpus carrying the one control GATE_BEARINGS actually
    claims, in the real family/file shape."""
    return _corpus(tmp_path, useq=("USEQ-E075330B", "USEQ-007A0FED"))


def test_a_failed_gate_moves_its_control_to_fail_with_the_detail_cited(tmp_path):
    corpus = ReadinessCorpus.open(_gate_corpus(tmp_path))
    gates = [("witnessed [M]", False, "author='sean' verified_by='sean' — verifier must differ")]
    a = readiness_corpus.assess_gates(gates, corpus)
    failed = {v.control_id: v for v in a.failed}
    assert "USEQ-E075330B" in failed
    v = failed["USEQ-E075330B"]
    assert v.instrument == "witnessed [M]"
    assert "verifier must differ" in v.evidence
    assert "docs/engineering/05-code-quality-and-implementation.md:3" in v.evidence


def test_a_passed_gate_is_blocked_never_pass(tmp_path):
    """A passing `witnessed [M]` means the floor string-check cleared — a
    different name is on record — not that a human actually reviewed anything.
    Rule 6 draws the line at Blocked, the same as a clean instrument."""
    corpus = ReadinessCorpus.open(_gate_corpus(tmp_path))
    gates = [("witnessed [M]", True, "author='sean' verified_by='loki' (attested — no seal declared)")]
    a = readiness_corpus.assess_gates(gates, corpus)
    assert [v.status for v in a.verdicts] == [Status.BLOCKED]
    assert "raises this control without a human's evidence answering it" in a.verdicts[0].evidence
    assert "verified_by='loki'" in a.verdicts[0].evidence  # the evidence is not withheld


def test_no_gate_outcome_can_produce_a_pass(tmp_path):
    corpus = ReadinessCorpus.open(_gate_corpus(tmp_path))
    for ok in (True, False):
        gates = [("witnessed [M]", ok, "detail")]
        a = readiness_corpus.assess_gates(gates, corpus)
        assert Status.PASS not in {v.status for v in a.verdicts}


def test_the_gate_path_inherits_the_type_level_no_pass_guarantee(tmp_path):
    """`assess_gates` cannot emit a Pass for the same structural reason `assess`
    cannot: not a guard it remembers to call, but the `Verdict` type refusing to
    hold a Pass at all. Were a later edit to add a gate branch that tried to
    write `Status.PASS` (e.g. promoting a passing `witnessed` to a real Pass),
    the constructor would raise inside `assess_gates`, not silently succeed —
    the "a convention is what a later edit forgets" failure closed at the type."""
    corpus = ReadinessCorpus.open(_gate_corpus(tmp_path))
    a = readiness_corpus.assess_gates([("witnessed [M]", True, "d")], corpus)
    assert {v.status for v in a.verdicts} == {Status.BLOCKED}  # passing gate → Blocked, never Pass
    with pytest.raises(ReadinessInvariantError):
        Verdict("USEQ-E075330B", Status.PASS, "witnessed [M]", "gate passed", "")


def test_a_gate_bearing_naming_a_control_this_corpus_lacks_is_skipped_not_invented(tmp_path):
    corpus = ReadinessCorpus.open(_corpus(tmp_path, useq=("USEQ-007A0FED",)))  # no USEQ-E075330B
    a = readiness_corpus.assess_gates([("witnessed [M]", False, "d")], corpus)
    assert a.verdicts == []
    assert "USEQ-E075330B" not in a.borne


def test_a_gate_with_no_bearing_is_reported_as_bearing_on_nothing(tmp_path):
    corpus = ReadinessCorpus.open(_gate_corpus(tmp_path))
    gates = [("witnessed [M]", False, "d"), ("import_pure_core [M]", True, "d")]
    a = readiness_corpus.assess_gates(gates, corpus)
    assert a.bearing_none == ["import_pure_core [M]"]
    assert "bear on no control in this corpus" in a.note()


def test_gate_base_name_normalization_strips_the_am_suffix():
    assert readiness_corpus._gate_base_name("witnessed [M]") == "witnessed"
    assert readiness_corpus._gate_base_name("own_repo [A]") == "own_repo"
    assert readiness_corpus._gate_base_name("host_repointed [A]") == "host_repointed"
    assert readiness_corpus._gate_base_name("attestation") == "attestation"  # no suffix, unchanged


def test_gate_bearings_normalize_before_lookup_so_the_suffix_does_not_matter(tmp_path):
    """GATE_BEARINGS is keyed by the base name; the gate's own [A]/[M] suffix
    in the reported name must not affect whether a bearing is found."""
    corpus = ReadinessCorpus.open(_gate_corpus(tmp_path))
    a = readiness_corpus.assess_gates([("witnessed [M]", False, "d")], corpus)
    assert "USEQ-E075330B" in a.borne


def test_every_gate_bearing_states_both_why_it_bears_and_what_it_cannot_show():
    for gate, bearings in readiness_corpus.GATE_BEARINGS.items():
        assert bearings, f"{gate} is in the table with no bearings"
        for b in bearings:
            assert b.why.strip() and b.limit.strip(), f"{gate}/{b.control_id}"


def test_the_gate_bearing_table_holds_only_a_conservative_witnessed_mapping():
    """The other nine gates were read and rejected (see the module comment
    above GATE_BEARINGS and the design doc) — this pins the deliberately small
    result against a future regex-shaped expansion."""
    assert set(readiness_corpus.GATE_BEARINGS) == {"witnessed"}


@pytest.mark.skipif(not _LIVE, reason=f"no real corpus injected at ${readiness_corpus.ENV_VAR}")
def test_live_every_gate_bearing_names_a_control_the_real_corpus_actually_contains():
    corpus = ReadinessCorpus.open(_LIVE)
    missing = [b.control_id for bs in readiness_corpus.GATE_BEARINGS.values() for b in bs
               if corpus.get(b.control_id) is None]
    assert not missing, f"gate bearings name controls absent from the real corpus: {missing}"
