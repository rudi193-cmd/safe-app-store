"""Tests for tools/store_reconcile.py — the declared-vs-materialized reconciler.

This is the full test matrix docs/design/store-reconciler.md §5 names: a case
per verdict (missing / source_changed / up_to_date / stale / declared_absent),
the fingerprint-honesty trio (mtime / version / code-bytes are NOT consulted),
the additive-only + idempotent + --allow-delete apply guards, the first-class
`skipped` bucket, the fail-closed and CLI contract, and the shared-seam proof
that the core is store-agnostic (byte-identity + a cp materializer reproduce
propagate-engine.sh's =/~/+/override behavior).

Same shape as tests/test_p3_generated_catalog_fields.py: a synthetic tree under
tmp_path and the tool spec-loaded from tools/ (it lives beside catalog_lint.py,
which is imported for the "make the gate pass" test). Stdlib + pytest only.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent


def _spec_load(name, rel):
    spec = importlib.util.spec_from_file_location(name, _REPO / rel)
    module = importlib.util.module_from_spec(spec)
    # Register before exec: dataclasses (3.14) resolves __module__ via
    # sys.modules while processing the class, the same reason the other tool
    # suites (test_readiness_drift.py) register their spec-loaded modules.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


sr = _spec_load("store_reconcile", "tools/store_reconcile.py")
catalog_lint = _spec_load("catalog_lint", "tools/catalog_lint.py")


# ── fixture builders ─────────────────────────────────────────────────────────

def _cat(app_id, *, status="building", path="__AUTO__", tier="playground",
         majors=("python",), **kw):
    e = {"id": app_id, "name": app_id, "description": "x", "status": status}
    if path == "__AUTO__":
        e["path"] = f"apps/{app_id}"
    elif path is not None:
        e["path"] = path
    if tier is not None:
        e["tier"] = tier
    if majors is not None:
        e["majors"] = list(majors)
    e.update(kw)
    return e


def _stored(app_id, *, majors=("python",), state="building", major=None,
            location=None, relation=None, anchor=None):
    return {"_major": major or majors[0], "app_id": app_id, "majors": list(majors),
            "relation": relation, "anchor": anchor,
            "location": location or f"apps/{app_id}", "maker": "USER",
            "lane": None, "state": state}


def _promoted(app_id, *, major="python"):
    return {"_major": major, "app_id": app_id, "verdict": "PROMOTED", "major": major}


def _manifest(app_id, name=None):
    return {"app_id": app_id, "name": name or app_id, "version": "1.0.0"}


def _build_repo(tmp_path, *, catalog=(), majors=("python", "node", "browser"),
                stored=(), promoted=(), pending=(), apps=()):
    """apps items: (dir_name, manifest_dict_or_None)."""
    (tmp_path / ".willow" / "store").mkdir(parents=True)
    (tmp_path / ".willow" / "store" / "catalog.json").write_text(json.dumps(
        {"version": "1.0", "store": "t", "description": "d", "apps": list(catalog)},
        indent=2))
    for major in majors:
        (tmp_path / "stores" / major / "stored").mkdir(parents=True)
        (tmp_path / "stores" / major / "promoted").mkdir(parents=True)
    for rec in stored:
        rec = dict(rec)
        major = rec.pop("_major")
        (tmp_path / "stores" / major / "stored" / f"{rec['app_id']}.json").write_text(
            json.dumps(rec, indent=2))
    for rec in promoted:
        rec = dict(rec)
        major = rec.pop("_major")
        (tmp_path / "stores" / major / "promoted" / f"{rec['app_id']}.json").write_text(
            json.dumps(rec, indent=2))
    (tmp_path / "stores" / "pending.json").write_text(
        json.dumps({"pending": list(pending)}, indent=2))
    for name, manifest in apps:
        d = tmp_path / "apps" / name
        d.mkdir(parents=True)
        if manifest is not None:
            (d / "safe-app-manifest.json").write_text(json.dumps(manifest))
    return tmp_path


def _verdicts(report):
    return {v.key: v.verdict for v in report.verdicts}


# ── 1-9: verdict classification ──────────────────────────────────────────────

def test_1_declared_only_resolvable_is_missing(tmp_path):
    repo = _build_repo(
        tmp_path,
        catalog=[_cat("foo")],
        stored=[_stored("foo")],
        apps=[],  # no apps/foo on disk
    )
    assert _verdicts(sr.run_reconcile(repo)) == {"foo": "missing"}


def test_2_materialized_only_not_pending_is_stale(tmp_path):
    repo = _build_repo(tmp_path, catalog=[], apps=[("bar", _manifest("bar"))])
    assert _verdicts(sr.run_reconcile(repo)) == {"bar": "stale"}


def test_3_both_present_equal_is_up_to_date(tmp_path):
    repo = _build_repo(
        tmp_path,
        catalog=[_cat("foo", majors=["python"], status="building")],
        stored=[_stored("foo", majors=["python"], state="building")],
        apps=[("foo", _manifest("foo"))],
    )
    assert _verdicts(sr.run_reconcile(repo)) == {"foo": "up_to_date"}


def test_4_majors_differ_is_source_changed_naming_majors(tmp_path):
    repo = _build_repo(
        tmp_path,
        catalog=[_cat("foo", majors=["python", "node"])],
        stored=[_stored("foo", majors=["python"], relation=None)],
        apps=[("foo", _manifest("foo"))],
    )
    report = sr.run_reconcile(repo)
    v = report.by_verdict()["source_changed"][0]
    assert v.key == "foo"
    assert "majors" in v.diverging


def test_5_status_ne_state_is_source_changed(tmp_path):
    repo = _build_repo(
        tmp_path,
        catalog=[_cat("foo", status="building")],
        stored=[_stored("foo", state="gated")],
        apps=[("foo", _manifest("foo"))],
    )
    v = sr.run_reconcile(repo).by_verdict()["source_changed"][0]
    assert v.key == "foo" and "status" in v.diverging


def test_6_manifest_app_id_ne_dir_is_source_changed(tmp_path):
    repo = _build_repo(
        tmp_path,
        catalog=[_cat("foo")],
        stored=[_stored("foo")],
        apps=[("foo", _manifest("something-else"))],
    )
    v = sr.run_reconcile(repo).by_verdict()["source_changed"][0]
    assert v.key == "foo" and "app_id" in v.diverging


def test_7_pending_with_reason_is_declared_absent_never_missing_or_stale(tmp_path):
    repo = _build_repo(
        tmp_path,
        catalog=[_cat("grove", path=None, tier=None, majors=None, status="building",
                      repository="https://example/grove")],
        pending=[{"app_id": "grove", "reason": "unreachable", "blocked_on": "x"}],
    )
    verdicts = _verdicts(sr.run_reconcile(repo))
    assert verdicts == {"grove": "declared_absent"}
    assert "missing" not in verdicts.values() and "stale" not in verdicts.values()


def test_8_promoted_record_plus_directory_is_up_to_date(tmp_path):
    repo = _build_repo(
        tmp_path,
        catalog=[_cat("foo", tier="promoted", majors=["python"], status="gated")],
        promoted=[_promoted("foo", major="python")],
        apps=[("foo", _manifest("foo"))],
    )
    assert _verdicts(sr.run_reconcile(repo)) == {"foo": "up_to_date"}


def test_9_empty_declared_and_materialized_is_empty_report(tmp_path):
    repo = _build_repo(tmp_path)
    report = sr.run_reconcile(repo)
    assert report.verdicts == []
    assert report.has_drift() is False


# ── 10-12: fingerprint honesty ───────────────────────────────────────────────

def test_10_different_mtimes_identical_facts_is_up_to_date(tmp_path):
    repo = _build_repo(
        tmp_path,
        catalog=[_cat("foo")],
        stored=[_stored("foo")],
        apps=[("foo", _manifest("foo"))],
    )
    # Stamp the app dir and manifest with a wildly different mtime — a fresh
    # checkout gives every file the same instant, so mtime must not be a signal.
    manifest = repo / "apps" / "foo" / "safe-app-manifest.json"
    os.utime(manifest, (1_000_000, 1_000_000))
    os.utime(repo / "apps" / "foo", (1_000_000, 1_000_000))
    assert _verdicts(sr.run_reconcile(repo)) == {"foo": "up_to_date"}


def test_11_no_version_on_either_side_still_classifies(tmp_path):
    manifest = _manifest("foo")
    manifest.pop("version")
    repo = _build_repo(
        tmp_path,
        catalog=[_cat("foo")],  # no version key
        stored=[_stored("foo")],  # keeping records never carry version
        apps=[("foo", manifest)],
    )
    assert _verdicts(sr.run_reconcile(repo)) == {"foo": "up_to_date"}


def test_12_changing_code_bytes_without_facts_is_up_to_date(tmp_path):
    repo = _build_repo(
        tmp_path,
        catalog=[_cat("foo")],
        stored=[_stored("foo")],
        apps=[("foo", _manifest("foo"))],
    )
    app_py = repo / "apps" / "foo" / "app.py"
    app_py.write_text("print('one')\n")
    assert _verdicts(sr.run_reconcile(repo)) == {"foo": "up_to_date"}
    app_py.write_text("print('two — totally different bytes')\n")
    assert _verdicts(sr.run_reconcile(repo)) == {"foo": "up_to_date"}


# ── 13-18: apply — additive & idempotent, the skipped bucket ──────────────────

def _snapshot(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes()
            for p in sorted(root.rglob("*")) if p.is_file()}


def test_13_apply_stale_writes_stub_existing_records_byte_unchanged(tmp_path):
    repo = _build_repo(
        tmp_path,
        catalog=[_cat("foo")],
        stored=[_stored("foo")],
        apps=[("foo", _manifest("foo")), ("bar", _manifest("bar"))],  # bar is stale
    )
    before_app = _snapshot(repo / "apps")
    before_stored = _snapshot(repo / "stores" / "python" / "stored")
    sr.run_apply(repo, heal_stale=True)
    pending = json.loads((repo / "stores" / "pending.json").read_text())
    assert any(e["app_id"] == "bar" for e in pending["pending"])  # stub written
    assert _snapshot(repo / "apps") == before_app  # directory byte-unchanged
    assert _snapshot(repo / "stores" / "python" / "stored") == before_stored


def test_14_apply_twice_is_idempotent_tree_byte_identical(tmp_path):
    repo = _build_repo(
        tmp_path,
        catalog=[_cat("foo", majors=["node"])],  # drifted from keeping -> source_changed
        stored=[_stored("foo", majors=["python"])],
        apps=[("foo", _manifest("foo"))],
    )
    sr.run_apply(repo)
    after_first = _snapshot(repo)
    _report, result = sr.run_apply(repo)
    assert result.applied == []  # nothing left to do
    assert _snapshot(repo) == after_first  # byte-identical second run


def test_15_apply_source_changed_realigns_catalog_only(tmp_path):
    repo = _build_repo(
        tmp_path,
        catalog=[_cat("foo", majors=["node"], status="gated")],
        stored=[_stored("foo", majors=["python"], state="building")],
        promoted=[],
        apps=[("foo", _manifest("foo"))],
    )
    before_stored = _snapshot(repo / "stores" / "python" / "stored")
    sr.run_apply(repo)
    catalog = json.loads((repo / ".willow" / "store" / "catalog.json").read_text())
    entry = next(e for e in catalog["apps"] if e["id"] == "foo")
    assert entry["majors"] == ["python"]  # realigned to keeping record
    assert entry["status"] == "building"
    assert _snapshot(repo / "stores" / "python" / "stored") == before_stored  # untouched


def test_16_apply_never_deletes_stale_without_flag_skipped_would_delete(tmp_path):
    repo = _build_repo(tmp_path, catalog=[], apps=[("bar", _manifest("bar"))])
    _report, result = sr.run_apply(repo)  # no --allow-delete, no --heal-stale
    reasons = {e["key"]: e["reason"] for e in result.skipped}
    assert "would_delete" in reasons["bar"]
    assert (repo / "apps" / "bar").is_dir()  # not removed


def test_16b_allow_delete_archives_not_removes(tmp_path):
    repo = _build_repo(tmp_path, catalog=[], apps=[("bar", _manifest("bar"))])
    _report, result = sr.run_apply(repo, allow_delete=True)
    assert any(e["key"] == "bar" for e in result.applied)
    assert not (repo / "apps" / "bar").exists()  # moved out of apps/
    assert (repo / "_archived_apps" / "bar").is_dir()  # archived, not deleted


def test_17_apply_missing_routes_to_skipped_no_code_fabricated(tmp_path):
    repo = _build_repo(
        tmp_path,
        catalog=[_cat("foo")],
        stored=[_stored("foo")],
        apps=[],  # apps/foo absent -> missing
    )
    _report, result = sr.run_apply(repo)
    reasons = {e["key"]: e["reason"] for e in result.skipped}
    assert "path_gone" in reasons["foo"] or "no_materializer" in reasons["foo"]
    assert not (repo / "apps" / "foo").exists()  # no code conjured


def test_18_stub_needing_human_field_written_blank_skipped_needs_human(tmp_path):
    repo = _build_repo(tmp_path, catalog=[], apps=[("bar", _manifest("bar"))])
    _report, result = sr.run_apply(repo, heal_stale=True)
    reasons = {e["key"]: e["reason"] for e in result.skipped}
    assert "needs_human" in reasons["bar"]
    pending = json.loads((repo / "stores" / "pending.json").read_text())
    stub = next(e for e in pending["pending"] if e["app_id"] == "bar")
    assert stub["reason"] == "" and stub["blocked_on"] == ""  # never invented


# ── 19-22: fail-closed & CLI contract ────────────────────────────────────────

def test_19_malformed_catalog_fails_closed_no_writes(tmp_path, monkeypatch, capsys):
    _build_repo(tmp_path, catalog=[])
    (tmp_path / ".willow" / "store" / "catalog.json").write_text("{ not json")
    before = _snapshot(tmp_path)
    monkeypatch.setattr(sr, "REPO", tmp_path)
    assert sr.main(["--apply"]) == 2  # non-zero
    assert _snapshot(tmp_path) == before  # no writes


def test_20_check_exit_code_tracks_drift(tmp_path, monkeypatch):
    drifting = _build_repo(
        tmp_path / "a",
        catalog=[_cat("foo")], stored=[_stored("foo")], apps=[],  # missing
    )
    monkeypatch.setattr(sr, "REPO", drifting)
    assert sr.main([]) == 1  # drift -> non-zero

    clean = _build_repo(
        tmp_path / "b",
        catalog=[_cat("foo")], stored=[_stored("foo")],
        apps=[("foo", _manifest("foo"))],
    )
    monkeypatch.setattr(sr, "REPO", clean)
    assert sr.main([]) == 0  # reconciled -> zero


def test_21_json_emits_report_and_apply_shapes(tmp_path, monkeypatch, capsys):
    repo = _build_repo(
        tmp_path,
        catalog=[_cat("foo", majors=["node"])],
        stored=[_stored("foo", majors=["python"])],
        apps=[("foo", _manifest("foo"))],
    )
    monkeypatch.setattr(sr, "REPO", repo)

    sr.main(["--json"])
    report = json.loads(capsys.readouterr().out)
    assert set(report) == {"verdicts", "counts"}
    assert report["verdicts"][0]["verdict"] == "source_changed"

    sr.main(["--apply", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert set(payload) == {"report", "apply"}
    assert set(payload["apply"]) == {"applied", "skipped", "noop"}


def test_22_after_apply_catalog_lint_strict_passes(tmp_path, monkeypatch):
    repo = _build_repo(
        tmp_path,
        majors=("python",),
        catalog=[_cat("foo", majors=["node"], status="building", tier="playground")],
        stored=[_stored("foo", majors=["python"], state="building")],
        apps=[("foo", _manifest("foo"))],
    )
    # Before: the generated-field drift is exactly what catalog_lint fails on.
    monkeypatch.setattr(catalog_lint, "REPO", repo)
    errors_before, _ = catalog_lint.lint()
    assert errors_before  # lint is red

    sr.run_apply(repo)  # the healer

    errors_after, _ = catalog_lint.lint()
    assert errors_after == []  # the reconciler made the existing gate green


# ── 23: shared-seam proof (the core is store-agnostic) ────────────────────────

def test_23_core_reproduces_propagate_engine_with_byte_identity_and_cp(tmp_path):
    """Drive the SAME core (sr.reconcile / sr.apply) with a byte-identity
    fingerprint and a cp materializer over two temp dirs — almanac-data's
    propagate-engine.sh seams. `=`/`~`/`+`/override must all reproduce, proving
    nothing store-specific leaked into the core."""
    template = tmp_path / "template"
    vertical = tmp_path / "vertical"
    template.mkdir()
    vertical.mkdir()
    (template / "same.txt").write_text("A")       # = up_to_date
    (vertical / "same.txt").write_text("A")
    (template / "changed.txt").write_text("NEW")  # ~ source_changed
    (vertical / "changed.txt").write_text("OLD")
    (template / "new.txt").write_text("C")        # + missing (template has, vertical lacks)
    (vertical / "override.txt").write_text("LOCAL")  # o local override -> exempt

    declared = {p.name: p for p in template.iterdir()}
    materialized = {p.name: p for p in vertical.iterdir()}

    def byte_fp(path):
        return {"sha": hashlib.sha256(path.read_bytes()).hexdigest()}

    report = sr.reconcile(
        declared, materialized,
        fingerprint_declared=byte_fp, fingerprint_materialized=byte_fp,
        exempt=frozenset({"override.txt"}),
    )
    assert _verdicts(report) == {
        "same.txt": "up_to_date",
        "changed.txt": "source_changed",
        "new.txt": "missing",
        "override.txt": "declared_absent",
    }

    def cp(v, opts):
        shutil.copyfile(declared[v.key], vertical / v.key)
        return sr.ActionResult("applied", "cp")

    result = sr.apply(report, actions={"missing": cp, "source_changed": cp})
    assert {e["key"] for e in result.applied} == {"changed.txt", "new.txt"}
    assert (vertical / "new.txt").read_text() == "C"      # copied in
    assert (vertical / "changed.txt").read_text() == "NEW"  # realigned
    assert (vertical / "override.txt").read_text() == "LOCAL"  # untouched
