"""Tests for the store refit's P2 gate: promote_check.py's --record path.

Each test builds a synthetic candidate *and* a synthetic stores/ tree under
tmp_path, and points promote_check.STORES at the latter via monkeypatch, so
these never write into the real stores/. Same shape as
tests/test_p1_keeping_records.py, for the same reason: a gate is only proven by
watching it refuse.

The candidate built by `_candidate()` clears every gate for real — it runs a
real pytest subprocess, gets scanned by the real vault-leak lint, and has its
core parsed by the real AST checks. Nothing here stubs the verdict except the
one test that has to (see `test_pass_with_self_verification_writes_nothing`).

Deliberately not covered: the first *real* records, for Nestor and Jeles. Their
extracted candidate directories are not in this repository and are not
reachable from CI — see docs/store_refit_plan.md's P2 note. Minting a record
from an invented attestation would be the exact falsehood the gate exists to
refuse, so the mechanism is proven on synthetics and the real minting is
recorded as deferred rather than faked.
"""
import importlib.util
import json
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "promote_check", _REPO / "stores" / "promote_check.py"
)
promote_check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(promote_check)


# ── fixtures ──────────────────────────────────────────────────────────────────

def _stores(tmp_path, majors=("python", "node")) -> Path:
    """A stores/ root with real majors — a major is a dir with both tiers."""
    root = tmp_path / "stores"
    for major in majors:
        (root / major / "stored").mkdir(parents=True)
        (root / major / "promoted").mkdir(parents=True)
    return root


def _candidate(tmp_path, **attestation) -> Path:
    """An extracted candidate that genuinely passes every gate in check()."""
    cand = tmp_path / "cand"
    (cand / "widget").mkdir(parents=True)
    (cand / "tests").mkdir()

    att = {
        "app_id": "widget",
        "author": "sean",
        "verified_by": "loki",
        "repo_url": "https://github.com/example/widget",
        "host": "willow-2.0",
        "core_module": "widget",
        "semantic_seam": "widget.matcher:Matcher",
        "host_repointed": True,
    }
    att.update(attestation)
    (cand / "promotion.json").write_text(json.dumps(att))
    (cand / "pyproject.toml").write_text('[project]\nname = "widget"\nversion = "0.1.0"\n')
    (cand / "tests" / "test_ok.py").write_text("def test_ok():\n    assert True\n")
    (cand / "widget" / "__init__.py").write_text('"""widget core."""\n')
    (cand / "widget" / "matcher.py").write_text(
        "class Matcher:\n    def match(self, a, b):\n        return a == b\n")
    return cand


def _snapshot(root: Path) -> dict[str, str]:
    """Every path under root, with file contents — so 'untouched' can be
    asserted as an equality rather than as an absence of one known file."""
    return {
        str(p.relative_to(root)): (p.read_text() if p.is_file() else "<dir>")
        for p in sorted(root.rglob("*"))
    }


# ── the happy path: a witnessed PASS leaves a mark ────────────────────────────

def test_pass_with_distinct_verifier_writes_a_record(tmp_path, monkeypatch):
    stores = _stores(tmp_path)
    cand = _candidate(tmp_path)
    monkeypatch.setattr(promote_check, "STORES", stores)

    rc = promote_check.main([str(cand), "--record"])
    assert rc == 0, "a witnessed PASS must record and exit 0"

    out = stores / "python" / "promoted" / "widget.json"
    assert out.is_file(), f"expected a record at {out}"
    rec = json.loads(out.read_text())
    assert rec["verdict"] == "PROMOTED"
    assert rec["repo_url"] == "https://github.com/example/widget"
    assert rec["verified_by"] == "loki" and rec["author"] == "sean"
    assert rec["major"] == "python"


def test_record_carries_every_gate_individually(tmp_path, monkeypatch):
    """Not a count, not a summary: one entry per gate check() emitted.

    docs/store_refit_plan.md says "the eight gate results"; check() emits nine
    today because the B13 audit added vault_leak after #88. The record follows
    check(), so it cannot go stale the way a written-down count does.
    """
    stores = _stores(tmp_path)
    cand = _candidate(tmp_path)
    monkeypatch.setattr(promote_check, "STORES", stores)
    promote_check.main([str(cand), "--record"])

    rec = json.loads((stores / "python" / "promoted" / "widget.json").read_text())
    expected = [g for g, _, _ in promote_check.check(cand)]
    assert [g["gate"] for g in rec["gates"]] == expected
    assert len(expected) >= 8, "the promotion bar is at least the eight gates of #88"
    assert all(g["ok"] for g in rec["gates"])
    assert all(g["detail"] for g in rec["gates"]), "a gate result without a detail is a tick-box"


def test_without_the_flag_nothing_is_written(tmp_path, monkeypatch):
    """--record is opt-in; a plain run keeps its pre-P2 behaviour exactly."""
    stores = _stores(tmp_path)
    cand = _candidate(tmp_path)
    monkeypatch.setattr(promote_check, "STORES", stores)
    before = _snapshot(stores)

    assert promote_check.main([str(cand)]) == 0
    assert _snapshot(stores) == before


# ── edge 1: proposing and ratifying in the same hand (§0.2) ───────────────────

def test_pass_with_self_verification_writes_nothing(tmp_path, monkeypatch, capsys):
    """The plan's first edge: *a PASS* with verified_by == author.

    check() would normally deny this at the `witnessed [M]` gate, so the only
    way to reach the writer with an all-PASS verdict is to hand it one. That is
    the point of the test — it proves the refusal lives in the writer and is
    not inherited from a gate that could be reordered, renamed or skipped.
    """
    stores = _stores(tmp_path)
    cand = _candidate(tmp_path, verified_by="sean")  # == author
    monkeypatch.setattr(promote_check, "STORES", stores)
    monkeypatch.setattr(promote_check, "check",
                        lambda c: [("witnessed [M]", True, "forced pass"),
                                   ("own_repo [A]", True, "forced pass")])
    before = _snapshot(stores)

    rc = promote_check.main([str(cand), "--record"])
    assert rc != 0, "a self-verified promotion must exit non-zero"
    assert _snapshot(stores) == before, "a self-verified promotion must write nothing"
    assert "same hand" in capsys.readouterr().out


def test_self_verification_is_also_denied_by_the_gate_itself(tmp_path, monkeypatch):
    """Belt and braces: unforced, the same attestation never reaches PASS."""
    stores = _stores(tmp_path)
    cand = _candidate(tmp_path, verified_by="sean")
    monkeypatch.setattr(promote_check, "STORES", stores)
    before = _snapshot(stores)

    assert promote_check.main([str(cand), "--record"]) != 0
    assert _snapshot(stores) == before


def test_missing_verifier_writes_nothing(tmp_path, monkeypatch):
    """An absent witness is not a passing witness — fail-closed, not open."""
    stores = _stores(tmp_path)
    cand = _candidate(tmp_path, verified_by="")
    monkeypatch.setattr(promote_check, "STORES", stores)
    monkeypatch.setattr(promote_check, "check", lambda c: [("forced [M]", True, "x")])
    before = _snapshot(stores)

    assert promote_check.main([str(cand), "--record"]) != 0
    assert _snapshot(stores) == before


# ── edge 2: any gate fails → stores/ is untouched ─────────────────────────────

def test_failed_gate_leaves_the_store_untouched(tmp_path, monkeypatch):
    stores = _stores(tmp_path)
    cand = _candidate(tmp_path, host_repointed=False)  # breaks host_repointed [A]
    monkeypatch.setattr(promote_check, "STORES", stores)
    before = _snapshot(stores)

    assert promote_check.main([str(cand), "--record"]) != 0
    assert _snapshot(stores) == before, "a denied candidate must leave no trace"


def test_failing_tests_leave_the_store_untouched(tmp_path, monkeypatch):
    """A mechanical gate, not just an attested one: the suite actually fails."""
    stores = _stores(tmp_path)
    cand = _candidate(tmp_path)
    (cand / "tests" / "test_ok.py").write_text("def test_ok():\n    assert False\n")
    monkeypatch.setattr(promote_check, "STORES", stores)
    before = _snapshot(stores)

    assert promote_check.main([str(cand), "--record"]) != 0
    assert _snapshot(stores) == before


def test_no_attestation_at_all_leaves_the_store_untouched(tmp_path, monkeypatch):
    stores = _stores(tmp_path)
    cand = _candidate(tmp_path)
    (cand / "promotion.json").unlink()
    monkeypatch.setattr(promote_check, "STORES", stores)
    before = _snapshot(stores)

    assert promote_check.main([str(cand), "--record"]) != 0
    assert _snapshot(stores) == before


# ── which store it files under ────────────────────────────────────────────────

def test_declared_major_is_honoured(tmp_path, monkeypatch):
    stores = _stores(tmp_path)
    cand = _candidate(tmp_path, major="node")
    monkeypatch.setattr(promote_check, "STORES", stores)

    assert promote_check.main([str(cand), "--record"]) == 0
    assert (stores / "node" / "promoted" / "widget.json").is_file()
    assert not (stores / "python" / "promoted" / "widget.json").exists()


def test_major_that_is_not_a_real_store_is_refused(tmp_path, monkeypatch):
    """An invented major must fail closed, not mint an eighth store."""
    stores = _stores(tmp_path)
    cand = _candidate(tmp_path, major="haskell")
    monkeypatch.setattr(promote_check, "STORES", stores)
    before = _snapshot(stores)

    assert promote_check.main([str(cand), "--record"]) != 0
    assert _snapshot(stores) == before
    assert not (stores / "haskell").exists(), "no store may be conjured by a record"


def test_majors_are_discovered_not_hardcoded(tmp_path):
    """A dir is a major only with both tiers present — same rule as
    catalog_lint._real_majors(), which P0 review changed from a hardcoded list."""
    stores = _stores(tmp_path, majors=("python", "rust"))
    (stores / "half" / "stored").mkdir(parents=True)      # no promoted/ → not a major
    (stores / "almanac").mkdir()                          # not a code store at all
    assert promote_check._real_majors(stores) == {"python", "rust"}


def test_undeclared_major_defaults_to_python_with_a_stated_reason(tmp_path):
    stores = _stores(tmp_path)
    major, why = promote_check.resolve_major({}, stores)
    assert major == "python"
    assert "Python-shaped" in why, "the default must carry its own reasoning"


# ── a promoted record is not overwritten ──────────────────────────────────────

def test_existing_record_is_not_silently_overwritten(tmp_path, monkeypatch):
    stores = _stores(tmp_path)
    cand = _candidate(tmp_path)
    monkeypatch.setattr(promote_check, "STORES", stores)
    assert promote_check.main([str(cand), "--record"]) == 0

    out = stores / "python" / "promoted" / "widget.json"
    out.write_text('{"verdict": "hand-edited"}\n')
    before = _snapshot(stores)

    assert promote_check.main([str(cand), "--record"]) != 0
    assert _snapshot(stores) == before, "re-minting must be deliberate, never silent"


# ── the API underneath, called directly ───────────────────────────────────────

def test_record_promotion_refuses_a_result_list_with_any_failure(tmp_path):
    stores = _stores(tmp_path)
    cand = _candidate(tmp_path)
    written, reason = promote_check.record_promotion(
        cand, [("a [M]", True, "ok"), ("b [M]", False, "nope")], stores_root=stores)
    assert written is None and "NOT PROMOTED" in reason


def test_record_promotion_refuses_an_empty_result_list(tmp_path):
    """No gates run is not the same as every gate passing — `all([])` is True."""
    stores = _stores(tmp_path)
    cand = _candidate(tmp_path)
    written, reason = promote_check.record_promotion(cand, [], stores_root=stores)
    assert written is None and "NOT PROMOTED" in reason
