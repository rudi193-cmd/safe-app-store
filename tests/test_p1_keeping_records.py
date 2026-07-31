"""Tests for the store refit's P1 gate: tools/catalog_lint.py's lint_records().

Each test builds a synthetic repo under tmp_path and points catalog_lint.REPO
at it via monkeypatch, so these never touch the real stores/ or apps/ trees.
Each check gets a case that should pass and a mutated case that should fail —
"a gate that cannot fail is not a gate."
"""
import importlib.util
import json
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "catalog_lint", _REPO / "tools" / "catalog_lint.py"
)
catalog_lint = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(catalog_lint)


def _build_repo(tmp_path, majors=("python", "node"), apps=(), records=(), pending=None):
    (tmp_path / "apps").mkdir()
    for app_id in apps:
        (tmp_path / "apps" / app_id).mkdir()

    (tmp_path / "stores").mkdir()
    for major in majors:
        (tmp_path / "stores" / major / "stored").mkdir(parents=True)
        (tmp_path / "stores" / major / "promoted").mkdir(parents=True)

    for rec in records:
        rec = dict(rec)
        major = rec.pop("_major")
        out = tmp_path / "stores" / major / "stored" / f"{rec['app_id']}.json"
        out.write_text(json.dumps(rec))

    if pending is not None:
        (tmp_path / "stores" / "pending.json").write_text(json.dumps({"pending": pending}))

    return tmp_path


def _record(app_id, majors, **kw):
    return {"_major": majors[0], "app_id": app_id, "majors": majors,
            "location": f"apps/{app_id}", "state": "building", **kw}


def test_a_clean_single_major_record_passes(tmp_path, monkeypatch):
    repo = _build_repo(
        tmp_path, apps=["foo"],
        records=[_record("foo", ["python"])],
    )
    monkeypatch.setattr(catalog_lint, "REPO", repo)
    errors, _ = catalog_lint.lint_records()
    assert errors == []


def test_uncovered_app_dir_fails(tmp_path, monkeypatch):
    repo = _build_repo(tmp_path, apps=["foo"], records=[])
    monkeypatch.setattr(catalog_lint, "REPO", repo)
    errors, _ = catalog_lint.lint_records()
    assert any("no keeping record" in e for e in errors)


def test_app_named_in_pending_is_not_flagged_as_uncovered(tmp_path, monkeypatch):
    repo = _build_repo(
        tmp_path, apps=["foo"], records=[],
        pending=[{"app_id": "foo", "reason": "spans crafts, no anchor rule fits",
                  "blocked_on": "relation vocabulary needs a new term"}],
    )
    monkeypatch.setattr(catalog_lint, "REPO", repo)
    errors, _ = catalog_lint.lint_records()
    assert not any("no keeping record" in e for e in errors)


def test_pending_entry_without_reason_fails(tmp_path, monkeypatch):
    repo = _build_repo(
        tmp_path, apps=["foo"], records=[],
        pending=[{"app_id": "foo"}],
    )
    monkeypatch.setattr(catalog_lint, "REPO", repo)
    errors, _ = catalog_lint.lint_records()
    assert any("missing reason/blocked_on" in e for e in errors)


def test_duplicate_app_id_across_records_fails(tmp_path, monkeypatch):
    repo = _build_repo(
        tmp_path, apps=["foo"],
        records=[_record("foo", ["python"]), _record("foo", ["node"])],
    )
    monkeypatch.setattr(catalog_lint, "REPO", repo)
    errors, _ = catalog_lint.lint_records()
    assert any("duplicate keeping record" in e for e in errors)


def test_unknown_major_fails(tmp_path, monkeypatch):
    # The record's *content* claims an unreal major; it still has to be filed
    # somewhere real to be discovered at all, so file it under python.
    rec = _record("foo", ["haskell"])
    rec["_major"] = "python"
    repo = _build_repo(tmp_path, apps=["foo"], records=[rec])
    monkeypatch.setattr(catalog_lint, "REPO", repo)
    errors, _ = catalog_lint.lint_records()
    assert any("not a real store" in e for e in errors)


def test_spanning_build_with_no_relation_fails(tmp_path, monkeypatch):
    repo = _build_repo(tmp_path, apps=["foo"], records=[_record("foo", ["python", "node"])])
    monkeypatch.setattr(catalog_lint, "REPO", repo)
    errors, _ = catalog_lint.lint_records()
    assert any("names no relation" in e for e in errors)


def test_spanning_build_with_named_relation_passes(tmp_path, monkeypatch):
    repo = _build_repo(
        tmp_path, apps=["foo"],
        records=[_record("foo", ["python", "node"], relation="sidecar")],
    )
    monkeypatch.setattr(catalog_lint, "REPO", repo)
    errors, _ = catalog_lint.lint_records()
    assert errors == []


def test_invalid_relation_name_fails(tmp_path, monkeypatch):
    repo = _build_repo(
        tmp_path, apps=["foo"],
        records=[_record("foo", ["python", "node"], relation="best-friends")],
    )
    monkeypatch.setattr(catalog_lint, "REPO", repo)
    errors, _ = catalog_lint.lint_records()
    assert any("invalid relation" in e for e in errors)


def test_differential_paired_without_anchor_fails(tmp_path, monkeypatch):
    repo = _build_repo(
        tmp_path, apps=["foo"],
        records=[_record("foo", ["python", "node"], relation="differential-paired")],
    )
    monkeypatch.setattr(catalog_lint, "REPO", repo)
    errors, _ = catalog_lint.lint_records()
    assert any("needs an anchor" in e for e in errors)


def test_anchor_not_among_majors_fails(tmp_path, monkeypatch):
    repo = _build_repo(
        tmp_path, apps=["foo"],
        records=[_record("foo", ["python", "node"], relation="differential-paired", anchor="rust")],
    )
    monkeypatch.setattr(catalog_lint, "REPO", repo)
    errors, _ = catalog_lint.lint_records()
    assert any("not among its own majors" in e for e in errors)


def test_differential_paired_with_valid_anchor_passes(tmp_path, monkeypatch):
    repo = _build_repo(
        tmp_path, apps=["foo"],
        records=[_record("foo", ["python", "node"], relation="differential-paired", anchor="python")],
    )
    monkeypatch.setattr(catalog_lint, "REPO", repo)
    errors, _ = catalog_lint.lint_records()
    assert errors == []


def test_location_that_does_not_resolve_fails(tmp_path, monkeypatch):
    repo = _build_repo(tmp_path, apps=["foo"], records=[_record("foo", ["python"], location="apps/nowhere")])
    monkeypatch.setattr(catalog_lint, "REPO", repo)
    errors, _ = catalog_lint.lint_records()
    assert any("does not resolve" in e for e in errors)


def test_url_location_for_a_loose_repo_is_accepted(tmp_path, monkeypatch):
    repo = _build_repo(
        tmp_path, apps=[],
        records=[{"_major": "python", "app_id": "elsewhere", "majors": ["python"],
                  "location": "https://github.com/example/elsewhere", "state": "building"}],
    )
    monkeypatch.setattr(catalog_lint, "REPO", repo)
    errors, _ = catalog_lint.lint_records()
    assert errors == []


def test_invalid_state_fails(tmp_path, monkeypatch):
    repo = _build_repo(tmp_path, apps=["foo"], records=[_record("foo", ["python"], state="vibing")])
    monkeypatch.setattr(catalog_lint, "REPO", repo)
    errors, _ = catalog_lint.lint_records()
    assert any("invalid state" in e for e in errors)


def test_filename_must_match_app_id(tmp_path, monkeypatch):
    repo = _build_repo(tmp_path, apps=["foo"], records=[])
    (repo / "stores" / "python" / "stored" / "wrong-name.json").write_text(
        json.dumps({"app_id": "foo", "majors": ["python"], "location": "apps/foo", "state": "building"})
    )
    monkeypatch.setattr(catalog_lint, "REPO", repo)
    errors, _ = catalog_lint.lint_records()
    assert any("!= app_id" in e for e in errors)
