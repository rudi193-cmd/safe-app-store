"""Tests for the status-vocabulary migration's effect on catalog_lint.py's
base lint() — the field-level checks (valid status, manifest requirement),
as distinct from lint_records() (P1) and lint_generated_fields() (P3), which
have their own test files.

lint() reads catalog.json and apps/ from REPO directly and also calls
lint_records()/lint_generated_fields() internally, so these tests build a
full synthetic repo (apps/, stores/, catalog.json) rather than calling a
narrower function directly — the point here is the base fields/manifest
behavior, and isolating it cleanly means the rest of the pipeline has to be
satisfied too, not stubbed around.
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


def _minimal_repo(tmp_path, status):
    """A single app, fully satisfying P1/P3 so only the status/manifest
    checks under test can produce a finding."""
    app_dir = tmp_path / "apps" / "foo"
    app_dir.mkdir(parents=True)
    if status != "seeded":
        # seeded is the one status this test deliberately leaves unmanifested
        # (it should only warn); every other status needs a real manifest to
        # avoid tripping the manifest-required check unrelated to what's
        # being tested here.
        (app_dir / "safe-app-manifest.json").write_text(
            json.dumps({"app_id": "foo"})
        )

    stores = tmp_path / "stores"
    for major in ("python",):
        (stores / major / "stored").mkdir(parents=True)
        (stores / major / "promoted").mkdir(parents=True)
    if status != "archived":
        record = {"app_id": "foo", "majors": ["python"], "location": "apps/foo",
                  "state": status if status != "seeded" else "seeded"}
        (stores / "python" / "stored" / "foo.json").write_text(json.dumps(record))

    catalog_dir = tmp_path / ".willow" / "store"
    catalog_dir.mkdir(parents=True)
    entry = {"id": "foo", "name": "foo", "description": "x", "status": status,
              "path": "apps/foo"}
    if status != "archived":
        entry["tier"] = "playground"
        entry["majors"] = ["python"]
    (catalog_dir / "catalog.json").write_text(
        json.dumps({"apps": [entry]}, indent=2)
    )
    return tmp_path


def test_old_vocabulary_value_is_rejected(tmp_path, monkeypatch):
    repo = _minimal_repo(tmp_path, "beta")
    monkeypatch.setattr(catalog_lint, "REPO", repo)
    errors, _ = catalog_lint.lint()
    assert any("invalid status" in e and "'beta'" in e for e in errors)


def test_each_new_vocabulary_value_is_accepted(tmp_path, monkeypatch):
    for status in ("seeded", "building", "gated", "stalled", "archived"):
        repo = _minimal_repo(tmp_path / status, status)
        monkeypatch.setattr(catalog_lint, "REPO", repo)
        errors, _ = catalog_lint.lint()
        assert not any("invalid status" in e for e in errors), (
            f"status={status!r} should be a valid status, got: {errors}"
        )


def test_building_app_without_manifest_errors(tmp_path, monkeypatch):
    repo = _minimal_repo(tmp_path, "building")
    (repo / "apps" / "foo" / "safe-app-manifest.json").unlink()
    monkeypatch.setattr(catalog_lint, "REPO", repo)
    errors, _ = catalog_lint.lint()
    assert any("without safe-app-manifest.json" in e for e in errors)


def test_gated_app_without_manifest_errors(tmp_path, monkeypatch):
    repo = _minimal_repo(tmp_path, "gated")
    (repo / "apps" / "foo" / "safe-app-manifest.json").unlink()
    monkeypatch.setattr(catalog_lint, "REPO", repo)
    errors, _ = catalog_lint.lint()
    assert any("without safe-app-manifest.json" in e for e in errors)


def test_stalled_app_without_manifest_errors(tmp_path, monkeypatch):
    repo = _minimal_repo(tmp_path, "stalled")
    (repo / "apps" / "foo" / "safe-app-manifest.json").unlink()
    monkeypatch.setattr(catalog_lint, "REPO", repo)
    errors, _ = catalog_lint.lint()
    assert any("without safe-app-manifest.json" in e for e in errors)


def test_seeded_app_without_manifest_only_warns(tmp_path, monkeypatch):
    """seeded is the one status where an absent manifest is a rough edge, not
    a lie — same softer treatment coming_soon used to get."""
    repo = _minimal_repo(tmp_path, "seeded")
    monkeypatch.setattr(catalog_lint, "REPO", repo)
    errors, warnings = catalog_lint.lint()
    assert not any("without safe-app-manifest.json" in e for e in errors)
    assert any("no safe-app-manifest.json yet" in w for w in warnings)
