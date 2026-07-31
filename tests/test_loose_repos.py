"""Tests for catalog_lint.py's lint_loose_repos() — the store refit's
resolution to one of docs/store_refit_plan.md's "Open gates" (decided
2026-07-31): a catalog entry naming a `repository` but no local `path` (code
the house cannot reach, like `grove`/`willow-grove`) must be named in
stores/pending.json with a reason, the same discipline P1 requires of an
apps/ build with no principled relation.

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


def _build_repo(tmp_path, pending=None):
    """lint_loose_repos() only reads stores/pending.json and
    stores/{major}/stored/ (via the same _load_pending_ids/_load_stored_records
    helpers lint_generated_fields() uses) — it takes the catalog's apps list
    as a plain argument, so no apps/ or catalog.json fixture is needed."""
    (tmp_path / "stores" / "python" / "stored").mkdir(parents=True)
    (tmp_path / "stores" / "python" / "promoted").mkdir(parents=True)
    if pending is not None:
        (tmp_path / "stores" / "pending.json").write_text(json.dumps({"pending": pending}))
    return tmp_path


def _loose_entry(app_id, status="building"):
    return {"id": app_id, "status": status,
            "repository": f"https://github.com/x/{app_id}"}


def test_a_loose_repo_named_in_pending_passes(tmp_path, monkeypatch):
    repo = _build_repo(tmp_path, pending=[
        {"app_id": "grove", "reason": "unreachable", "blocked_on": "repo access"},
    ])
    monkeypatch.setattr(catalog_lint, "REPO", repo)
    errors, _ = catalog_lint.lint_loose_repos([_loose_entry("grove")])
    assert errors == []


def test_a_loose_repo_not_named_anywhere_fails(tmp_path, monkeypatch):
    repo = _build_repo(tmp_path, pending=[])
    monkeypatch.setattr(catalog_lint, "REPO", repo)
    errors, _ = catalog_lint.lint_loose_repos([_loose_entry("grove")])
    assert any("grove" in e and "pending.json" in e for e in errors), errors


def test_an_archived_loose_repo_is_exempt(tmp_path, monkeypatch):
    repo = _build_repo(tmp_path, pending=[])
    monkeypatch.setattr(catalog_lint, "REPO", repo)
    errors, _ = catalog_lint.lint_loose_repos([_loose_entry("grove", status="archived")])
    assert errors == []


def test_a_loose_repo_with_a_real_keeping_record_also_passes(tmp_path, monkeypatch):
    repo = _build_repo(tmp_path, pending=[])
    record = {"app_id": "grove", "majors": ["python"], "location": "safe-app-grove",
              "state": "building"}
    (repo / "stores" / "python" / "stored" / "grove.json").write_text(json.dumps(record))
    monkeypatch.setattr(catalog_lint, "REPO", repo)
    errors, _ = catalog_lint.lint_loose_repos([_loose_entry("grove")])
    assert errors == []


def test_entries_with_a_path_are_untouched(tmp_path, monkeypatch):
    """lint_loose_repos() only applies to pathless repository entries — a
    normal apps/ entry with both a path and a repository (like
    oakenscrolls-office) is someone else's gate's problem."""
    repo = _build_repo(tmp_path, pending=[])
    monkeypatch.setattr(catalog_lint, "REPO", repo)
    entry = {"id": "oakenscrolls-office", "status": "building",
              "path": "apps/oakenscrolls-office", "repository": "https://github.com/x/y"}
    errors, _ = catalog_lint.lint_loose_repos([entry])
    assert errors == []
