"""Tests for tools/readiness_drift.py — the upstream-drift guard for the
Forge's readiness seam.

`stores/readiness_corpus.py`'s `BEARINGS` and `GATE_BEARINGS` pin a handful of
hand-authored claims to specific control IDs in a corpus that lives in another
repository and re-syncs upstream. `assess()` already fails closed on a bearing
whose control the corpus no longer has — it skips the bearing rather than
inventing evidence — but nothing PROACTIVELY says a bearing went stale. That
gap is `docs/design/the-forge-readiness.md`'s Open/next item this tool closes.

Three properties carry the module and are tested hardest, mirroring its own
exit contract:

  1. **Every referenced ID present → exit 0**, naming the corpus and the
     count verified. Built from the REAL tables, not a hardcoded ID list —
     the same trap `readiness_corpus.py`'s own `test_live_every_bearing_names_
     a_control_the_real_corpus_actually_contains` avoids, so this test still
     tracks `BEARINGS`/`GATE_BEARINGS` if either grows or shrinks.
  2. **One referenced ID missing → exit 1**, and the report names both the
     drifted ID and which table/key referenced it — the fix has to be
     findable without re-deriving which bearing broke.
  3. **No corpus injected → exit 2, never a silent 0.** A guard that cannot
     reach its corpus reporting "clean" would be worse than not running at
     all — the false all-clear `readiness_corpus.CorpusUnavailable` itself
     exists to rule out, one level up.

Invoked the way `tests/test_instrument_callgraph.py` invokes a `tools/`
executable: `subprocess.run` against the real interpreter, asserting the
process's actual exit code and printed output — the thing the tool's exit
contract promises, not an internal function's return value.

Stdlib + pytest only. The corpus is built in `tmp_path` in the real upstream
shape (see `tests/test_readiness_corpus.py`'s `_corpus` helper, replicated
minimally here); no network, no fleet binaries.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_TOOL = _REPO / "tools" / "readiness_drift.py"

_rc_spec = importlib.util.spec_from_file_location(
    "readiness_corpus", _REPO / "stores" / "readiness_corpus.py")
readiness_corpus = importlib.util.module_from_spec(_rc_spec)
sys.modules["readiness_corpus"] = readiness_corpus
_rc_spec.loader.exec_module(readiness_corpus)

_rd_spec = importlib.util.spec_from_file_location("readiness_drift", _TOOL)
readiness_drift = importlib.util.module_from_spec(_rd_spec)
sys.modules["readiness_drift"] = readiness_drift
_rd_spec.loader.exec_module(readiness_drift)


# ── a miniature corpus, in the real upstream shape ───────────────────────────

def _referenced_ids() -> set[str]:
    """Every control ID `BEARINGS`/`GATE_BEARINGS` actually reference, read
    off the live tables — never a hardcoded snapshot, so this file does not
    go stale the day a bearing is added or repointed."""
    ids: set[str] = set()
    for table in (readiness_corpus.BEARINGS, readiness_corpus.GATE_BEARINGS):
        for bearings in table.values():
            for b in bearings:
                ids.add(b.control_id)
    return ids


def _corpus(tmp_path: Path, ids) -> Path:
    """A corpus containing exactly `ids`, split into the two real families and
    written in the exact markdown shape `readiness_corpus.py`'s `_PRC`/`_USEQ`
    regexes parse — the same shape `tests/test_readiness_corpus.py`'s own
    `_corpus` helper builds, sized here to whatever the live tables need."""
    prc = sorted(i for i in ids if i.startswith("PRC-"))
    useq = sorted(i for i in ids if i.startswith("USEQ-"))
    root = tmp_path / "corpus"
    (root / "docs" / "checklists").mkdir(parents=True)
    (root / "docs" / "engineering").mkdir(parents=True)
    (root / "docs" / "checklists" / "03-source-build-supply-chain.md").write_text(
        "# Source\n\n" + "".join(f"- [ ] **{c}** — Control text for {c}.\n" for c in prc),
        encoding="utf-8")
    (root / "docs" / "engineering" / "05-code-quality-and-implementation.md").write_text(
        "# Code quality\n\n" + "".join(f"- [ ] **{c}** — Control text for {c}.\n" for c in useq),
        encoding="utf-8")
    return root


def _run(*args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_TOOL), *args],
        capture_output=True, text=True, cwd=_REPO, env=env,
    )


# ── the exit contract ─────────────────────────────────────────────────────────

def test_a_corpus_with_every_referenced_id_present_exits_clean(tmp_path):
    ids = _referenced_ids()
    assert ids, "BEARINGS/GATE_BEARINGS reference no controls — nothing to guard"
    corpus_root = _corpus(tmp_path, ids)

    result = _run("--corpus", str(corpus_root))

    assert result.returncode == 0, result.stdout + result.stderr
    # deduplicated count, not a sum over every bearing (PRC-07-015 alone is
    # named by both `census` and `hygiene` — one ID, one line in the count)
    assert f"{len(ids)} referenced control ID(s) verified present" in result.stdout
    assert "readiness corpus" in result.stdout or "Checklist" in result.stdout


def test_a_missing_referenced_id_drifts_with_its_referencing_site_named(tmp_path):
    ids = _referenced_ids()
    sites = readiness_drift._collect_sites(readiness_corpus)
    # PRC-07-015 is the load-bearing case: two DIFFERENT instruments (census,
    # hygiene) reference it, so dropping it also proves the report lists
    # every site, not just the first one found.
    victim = "PRC-07-015" if "PRC-07-015" in ids else sorted(ids)[0]
    victim_sites = sites[victim]
    assert victim_sites, f"{victim} has no recorded referencing site to assert on"

    corpus_root = _corpus(tmp_path, ids - {victim})
    result = _run("--corpus", str(corpus_root))

    assert result.returncode == 1, result.stdout + result.stderr
    assert victim in result.stdout
    for table, key in victim_sites:
        assert f"{table}[{key}]" in result.stdout, (table, key, result.stdout)
    assert f"1 of {len(ids)} referenced control ID(s) drifted" in result.stdout


def test_no_corpus_injected_exits_2_never_a_false_all_clear():
    env = {k: v for k, v in os.environ.items() if k != readiness_corpus.ENV_VAR}
    result = _run(env=env)

    assert result.returncode == 2, result.stdout + result.stderr
    assert "corpus unavailable" in (result.stdout + result.stderr).lower()
    assert "clean" not in result.stdout  # a guard that cannot run must not read as a pass


# ── the collection helper itself ─────────────────────────────────────────────

def test_collect_sites_deduplicates_ids_but_keeps_every_referencing_site():
    sites = readiness_drift._collect_sites(readiness_corpus)
    assert sites["PRC-07-015"] == {("BEARINGS", "census"), ("BEARINGS", "hygiene")}
    assert len(sites) == len(_referenced_ids())


if __name__ == "__main__":
    import tempfile

    failures = 0
    for name, fn in sorted(globals().items()):
        if not (name.startswith("test_") and callable(fn)):
            continue
        try:
            if "tmp_path" in fn.__code__.co_varnames[: fn.__code__.co_argcount]:
                with tempfile.TemporaryDirectory() as d:
                    fn(Path(d))
            else:
                fn()
            print(f"ok   {name}")
        except Exception as exc:
            failures += 1
            print(f"FAIL {name}\n{type(exc).__name__}: {exc}\n")
    raise SystemExit(1 if failures else 0)
