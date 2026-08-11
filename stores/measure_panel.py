#!/usr/bin/env python3
"""stores/measure_panel.py — The Forge's measuring panel.

The box (`rudi193-cmd/quick-stupids` PR #5) taught two things a builder-harness
has to internalize:

  1. **The failure is never in the step you were watching.** The box's real
     disease — a committed `error_log`, 93% of the repo — was named by FOUR
     unrelated instruments (redaction, heat-risk, token-budget, double-entry
     debt), none asked to look, all converging. The headline jokes were the
     distraction. Decision-checkpoints (the watched decisions) are structurally
     blind to this class: nobody *decides* the error_log. Only measuring the
     whole build catches it, and **convergence — several blind instruments
     naming the same artifact — is a far stronger signal than any one.**

  2. **Health is a claim about the harness, not the code.** sigmap scored the
     worst repo imaginable 100/100 health A and coverage D in the same breath,
     because "health" meant "did my own tooling run." A green harness on a
     rotten artifact is the trap. So this panel **reports its own coverage**:
     every run states which instruments ran, which couldn't, and what class of
     failure that blinds it to — a clean panel is never read as a sound build.

This module is the panel FRAMEWORK plus two dependency-free instruments
(`census`, `hygiene`). The richer instruments are the fleet's own
refuse-a-confident-wrong-answer tools — `codebase-memory-mcp` (call graph /
dead code `fan_in=0`, which caught the box's decoy that ranking and extraction
could not), `kartikeya` (execute, don't read — already bite 0's sandbox),
`oakenscrolls-office` (grade the model's own confidence), `smallcode` (its exact
token estimator over the census). Each is an `Instrument` adapter wired as it is
reached; until then the panel names it as an uncovered class (see honest
coverage above). Rule 11: reuse the tools that made willow, don't rebuild them —
the panel is the wiring, and the two pure instruments here are only the
dependency-free floor.

Convergent findings route into the `human_required` queue via
`checkpoint_governance.route_nudge` — the same outbox the engagement gate and
#67 nudges feed. A convergent finding is a `review` item a human should see;
the panel never blocks a build, it surfaces.

Store-side (D1): `apps/the-forge/` never imports this — a build does not measure
itself and mark its own homework.

Usage:
    python stores/measure_panel.py measure <build_dir>
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Protocol, runtime_checkable

_REPO = Path(__file__).resolve().parent.parent

_gov_spec = importlib.util.spec_from_file_location(
    "checkpoint_governance", _REPO / "stores" / "checkpoint_governance.py"
)
checkpoint_governance = importlib.util.module_from_spec(_gov_spec)
sys.modules["checkpoint_governance"] = checkpoint_governance
_gov_spec.loader.exec_module(checkpoint_governance)


class InstrumentUnavailable(Exception):
    """An instrument that could not run in this environment (a missing binary,
    an offline model, no bwrap). Raised by `measure()`; the panel records it as
    a COVERAGE GAP — a named class the harness could not see — never a crash.
    This is the box's honesty: DontFeedTheAI admitting its regex layer couldn't
    see the password, sigmap's health-vs-coverage split, made first-class."""


@dataclass(frozen=True)
class Finding:
    """One instrument's observation about one artifact (a path, relative to the
    build dir). `metric`/`value` are the instrument's own measure; `severity`
    is a coarse `low`/`med`/`high`; `detail` is human-facing."""

    instrument: str
    artifact: str
    metric: str
    value: object
    severity: str
    detail: str


@dataclass(frozen=True)
class ConvergentFinding:
    """An artifact named by >=2 DISTINCT instruments — the alarm. Convergence
    is the panel's strongest signal (the box's error_log, four witnesses)."""

    artifact: str
    instruments: tuple[str, ...]
    findings: tuple[Finding, ...]


# The measurement CLASSES a mature panel aspires to, each with the fleet tool
# that covers it. The panel names the ones NOT covered in a given run — so a
# green run is honestly incomplete rather than a false all-clear (the sigmap
# health-vs-coverage lesson). An instrument declares which class it `covers`.
ASPIRATIONAL_CLASSES: dict[str, str] = {
    "size": "census (or smallcode's token budget)",
    "hygiene": "the hygiene instrument",
    "call-graph": "codebase-memory-mcp (dead code / fan_in=0 — the box's decoy)",
    "execution": "kartikeya (run it, don't read it — bite 0's sandbox)",
    "calibration": "oakenscrolls-office (grade the model's own confidence)",
}


@dataclass
class PanelReport:
    findings: list[Finding]
    convergent: list[ConvergentFinding]
    ran: list[str]
    unavailable: list[tuple[str, str]]  # (instrument name, reason)
    not_covered: list[tuple[str, str]] = field(default_factory=list)  # (class, fleet tool)

    def coverage_note(self) -> str:
        """The sigmap lesson as a sentence the panel always emits: what ran,
        what couldn't, and — crucially — which measurement CLASSES had no
        instrument at all, named with the fleet tool that would cover them. A
        clean report still says 'I did not trace the call graph or execute,' so
        green is never mistaken for sound."""
        ran = ", ".join(self.ran) or "(none)"
        note = f"panel coverage: ran [{ran}]"
        if self.unavailable:
            gaps = "; ".join(f"{n} ({why})" for n, why in self.unavailable)
            note += f" — COULD NOT RUN [{gaps}]"  # InstrumentUnavailable OR errored (reason says which)
        if self.not_covered:
            missing = "; ".join(f"{cls} <- {tool}" for cls, tool in self.not_covered)
            note += f" — NOT COVERED AT ALL [{missing}]"
        note += (
            ". This is harness coverage, not a verdict on the artifact: a class "
            "no instrument measured is a class this panel could not see."
        )
        return note


@runtime_checkable
class Instrument(Protocol):
    """A measuring instrument. `name` is stable (used as the convergence key
    and the queue source). `measure(build_dir)` returns findings, or raises
    `InstrumentUnavailable` to declare a coverage gap. An instrument MEASURES
    (size, call graph, execution), it does not judge a design decision — that
    is the checkpoint's job; the panel catches what checkpoints can't see."""

    @property
    def name(self) -> str: ...

    def measure(self, build_dir: Path) -> list[Finding]: ...

    # `covers`: which ASPIRATIONAL_CLASSES label this instrument satisfies, so
    # the panel can name the classes left uncovered. Optional — the panel falls
    # back to the instrument's own name when absent. CONTRACT: set `covers` only
    # if this instrument really measures that class. The panel counts a class
    # covered when an instrument declaring it RAN (did not raise) — it cannot
    # tell a real measurement from a no-op stub, so a stub that sets `covers`
    # without measuring would falsely claim coverage. That honesty is the
    # adapter author's to keep; the panel names what it can and cannot verify.


# ── shared helpers ─────────────────────────────────────────────────────────

def _iter_files(build_dir: Path):
    """Yield the real files under `build_dir`, NOT following symlinks and
    skipping `.git`. Uses `os.walk(followlinks=False)` (rglob follows symlinked
    directories on 3.11) and skips symlinked FILES too — so a symlink aliasing
    the dominator can't mask the census alarm, and hygiene can't phantom-flag an
    alias. (Both holes were found by the adversarial audit of the first cut.)"""
    build_dir = Path(build_dir)
    for root, dirs, files in os.walk(build_dir, followlinks=False):
        dirs[:] = [d for d in dirs if d != ".git"]  # prune .git subtrees
        for name in files:
            p = Path(root) / name
            if p.is_symlink():
                continue  # skip alias/symlink files — they double-count and can mask
            yield p


def canonical_artifact(artifact: str, build_dir: Path) -> str:
    """The convergence key for an artifact path — normalized so two instruments
    naming the SAME file with different spellings still converge. WITHOUT this,
    `codebase-memory-mcp` emitting `/abs/build/src/x.py` and the census emitting
    `src/x.py` would never converge, silently swallowing the alarm the panel
    exists to raise (the audit's top finding). Normalizes: backslashes → `/`,
    an absolute path under `build_dir` → relative, a leading `./`, and collapsed
    separators. An absolute path OUTSIDE build_dir is left as-is (posix)."""
    s = str(artifact).replace("\\", "/")
    p = Path(s)
    if p.is_absolute():
        try:
            p = p.relative_to(Path(build_dir).resolve())
        except ValueError:
            try:
                p = p.relative_to(Path(build_dir))
            except ValueError:
                return PurePosixPath(s).as_posix()  # genuinely outside — keep, normalized
    parts = [part for part in PurePosixPath(str(p).replace("\\", "/")).parts if part not in (".", "")]
    return PurePosixPath(*parts).as_posix() if parts else ""


# ── the panel ────────────────────────────────────────────────────────────────

def run_panel(build_dir: Path, instruments: list[Instrument]) -> PanelReport:
    """Run each instrument across `build_dir`, collect findings, compute
    convergence (artifacts named by >=2 distinct instruments), and record honest
    coverage (what ran / what declared itself unavailable). An instrument that
    raises `InstrumentUnavailable` becomes a coverage gap; any OTHER exception
    also becomes a gap (with the exception text) rather than sinking the whole
    panel — one broken instrument must not blind the others."""
    build_dir = Path(build_dir)
    findings: list[Finding] = []
    ran: list[str] = []
    unavailable: list[tuple[str, str]] = []

    for inst in instruments:
        try:
            got = inst.measure(build_dir)
        except InstrumentUnavailable as e:
            unavailable.append((inst.name, str(e)))
            continue
        except Exception as e:  # noqa: BLE001 — a broken instrument is a gap, not a panel crash
            unavailable.append((inst.name, f"errored: {type(e).__name__}: {e}"))
            continue
        ran.append(inst.name)
        findings.extend(got)

    # convergence: group by the CANONICAL artifact key (so differently-spelled
    # paths for the same file still converge — see canonical_artifact), keep
    # those named by >=2 distinct instruments.
    by_artifact: dict[str, list[Finding]] = {}
    for f in findings:
        by_artifact.setdefault(canonical_artifact(f.artifact, build_dir), []).append(f)
    convergent: list[ConvergentFinding] = []
    for artifact, fs in by_artifact.items():
        names = sorted({f.instrument for f in fs})
        if len(names) >= 2:
            convergent.append(ConvergentFinding(artifact=artifact, instruments=tuple(names), findings=tuple(fs)))
    convergent.sort(key=lambda c: (-len(c.instruments), c.artifact))

    # honest coverage: which aspirational classes had an instrument that RAN.
    # A class covered only by an instrument that declared itself unavailable is
    # NOT covered — that is the whole point.
    covered_classes = {getattr(inst, "covers", inst.name) for inst in instruments if inst.name in ran}
    not_covered = [(cls, tool) for cls, tool in ASPIRATIONAL_CLASSES.items() if cls not in covered_classes]

    return PanelReport(
        findings=findings, convergent=convergent, ran=ran,
        unavailable=unavailable, not_covered=not_covered,
    )


def route(report: PanelReport, *, builder_id: str, root: Path) -> int:
    """Surface convergent findings into the `human_required` queue as `review`
    items (reusing `checkpoint_governance.route_nudge`, deduped by artifact).
    Returns the number of NEW items enqueued. Never blocks — the panel surfaces,
    a human decides. Single-instrument findings are recorded in the report but
    not routed: convergence is the bar for a human's attention (the box's whole
    point — one witness is a guess, several is a diagnosis)."""
    enqueued = 0
    for c in report.convergent:
        item = checkpoint_governance.route_nudge(
            builder_id,
            kind="review",
            title=f"convergent finding on {c.artifact} ({len(c.instruments)} instruments)",
            summary=(
                f"{', '.join(c.instruments)} independently flagged {c.artifact}. "
                + " | ".join(f"[{f.instrument}] {f.metric}={f.value}: {f.detail}" for f in c.findings)
            ),
            source_ref=f"converge:{c.artifact}",
            priority="high",
            root=root,
        )
        if item is not None:
            enqueued += 1
    return enqueued


# ── instrument 1: census (size share — the committed-log class) ──────────────

class CensusInstrument:
    """Flags any single file that is a disproportionate share of the build's
    total bytes — the `error_log`-at-93% class the box's token/redaction/heat/
    ledger instruments all converged on. A size census, not a tokenizer: the
    box showed the signal (one file dominating) is robust to the exact count,
    so this needs no dependency. `smallcode`'s `estimateTokens` is the precise-
    token adapter to swap in when a real token budget matters."""

    name = "census"
    covers = "size"

    def __init__(self, dominance: float = 0.40, min_files: int = 3):
        # A file is flagged only if it is BOTH a large absolute share (>=
        # dominance) AND dwarfs the next-largest file (>= 2x) — "one file
        # drowning the rest," not merely the biggest of a balanced few. And the
        # build must have at least `min_files` files: "dominance" is not a
        # concept in a 1-2 file toy, only in a repo a stray artifact can drown.
        self.dominance = dominance
        self.min_files = min_files

    def measure(self, build_dir: Path) -> list[Finding]:
        files = list(_iter_files(build_dir))  # real files, no symlinks, no .git
        if len(files) < self.min_files:
            return []
        sizes = {p: p.stat().st_size for p in files}
        total = sum(sizes.values())
        if total == 0:
            return []
        out: list[Finding] = []
        for p, sz in sizes.items():
            share = sz / total
            others_max = max((s for q, s in sizes.items() if q != p), default=0)
            if share >= self.dominance and sz >= 2 * others_max:
                rel = p.relative_to(build_dir).as_posix()
                out.append(Finding(
                    instrument=self.name, artifact=rel, metric="byte_share", value=round(share, 3),
                    severity="high" if share >= 0.6 else "med",
                    detail=f"{sz} bytes — {share:.0%} of the build, dwarfing every other file; one file dominating the repo is the box's headline pathology",
                ))
        return out


# ── instrument 2: hygiene (committed-by-accident smells) ─────────────────────

class HygieneInstrument:
    """Flags artifacts that look committed by accident — logs, backups, nested
    tarballs, DB lock files, editor/OS junk, load-bearing sentinels. Not size:
    a small stray `.bak` is a smell even when it isn't the biggest file. These
    are the box's own species, scaled down."""

    name = "hygiene"
    covers = "hygiene"

    _SUFFIXES = {".log", ".bak", ".old", ".tmp", ".swp", ".orig", ".tar", ".tgz",
                 ".gz", ".bz2", ".xz", ".7z", ".rar", ".zip", ".mdb", ".ldb", ".db"}
    _NAMES = {"error_log", "thumbs.db", ".ds_store", "do_not_delete.txt", "npdblock.net"}
    _NAME_CONTAINS = ("do_not_delete", "final_v2", "_backup", "copy of ")

    def measure(self, build_dir: Path) -> list[Finding]:
        out: list[Finding] = []
        for p in _iter_files(build_dir):  # real files, no symlinks, no .git
            name = p.name.lower()
            hit = (
                p.suffix.lower() in self._SUFFIXES
                or name in self._NAMES
                or any(s in name for s in self._NAME_CONTAINS)
            )
            if hit:
                rel = p.relative_to(build_dir).as_posix()
                out.append(Finding(
                    instrument=self.name, artifact=rel, metric="smell", value=p.suffix or name,
                    severity="med",
                    detail="looks committed by accident (log/backup/junk/sentinel) — the class that should never be in version control",
                ))
        return out


DEFAULT_INSTRUMENTS: list[Instrument] = [CensusInstrument(), HygieneInstrument()]


# ── CLI ──────────────────────────────────────────────────────────────────────

def _cmd_measure(args: argparse.Namespace) -> int:
    instruments = list(DEFAULT_INSTRUMENTS)
    if args.with_callgraph:
        # Lazy import: instrument_callgraph imports THIS module, so importing it
        # at module scope would cycle. It is opt-in because it needs the
        # external codebase-memory-mcp binary (the panel's DEFAULT stays pure).
        spec = importlib.util.spec_from_file_location(
            "instrument_callgraph", _REPO / "stores" / "instrument_callgraph.py"
        )
        icg = importlib.util.module_from_spec(spec)
        sys.modules["instrument_callgraph"] = icg
        spec.loader.exec_module(icg)
        instruments.append(icg.CallGraphInstrument())
    report = run_panel(Path(args.build_dir), instruments)
    print(json.dumps({
        "convergent": [
            {"artifact": c.artifact, "instruments": list(c.instruments)} for c in report.convergent
        ],
        "findings": [
            {"instrument": f.instrument, "artifact": f.artifact, "metric": f.metric,
             "value": f.value, "severity": f.severity} for f in report.findings
        ],
        "coverage": report.coverage_note(),
    }, indent=2))
    # exit 1 if the panel found convergence — a CI signal, though it never blocks a build itself
    return 1 if report.convergent else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="measure_panel.py")
    sub = p.add_subparsers(dest="command", required=True)
    m = sub.add_parser("measure", help="run the measuring panel across a build directory")
    m.add_argument("build_dir")
    m.add_argument("--with-callgraph", action="store_true",
                   help="also run the codebase-memory-mcp call-graph instrument (needs the binary)")
    m.set_defaults(func=_cmd_measure)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
