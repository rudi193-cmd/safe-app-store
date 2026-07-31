"""Tests for the store refit's P3 gate: catalog_lint.py's
lint_generated_fields().

Same shape as tests/test_p1_keeping_records.py: a synthetic stores/ tree under
tmp_path, catalog.json's "apps" list passed in directly (this function takes
it as an argument rather than reading a file, so no catalog.json fixture is
needed), and catalog_lint.REPO monkeypatched so stores/pending.json and the
records are read from the synthetic tree.
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


def _build_repo(tmp_path, majors=("python", "node"), stored=(), promoted=(), pending=None):
    (tmp_path / "stores").mkdir()
    for major in majors:
        (tmp_path / "stores" / major / "stored").mkdir(parents=True)
        (tmp_path / "stores" / major / "promoted").mkdir(parents=True)

    for rec in stored:
        rec = dict(rec)
        major = rec.pop("_major")
        out = tmp_path / "stores" / major / "stored" / f"{rec['app_id']}.json"
        out.write_text(json.dumps(rec))

    for rec in promoted:
        rec = dict(rec)
        major = rec.pop("_major")
        out = tmp_path / "stores" / major / "promoted" / f"{rec['app_id']}.json"
        out.write_text(json.dumps(rec))

    if pending is not None:
        (tmp_path / "stores" / "pending.json").write_text(json.dumps({"pending": pending}))

    return tmp_path


def _stored_record(app_id, majors, state, major=None):
    return {"_major": major or majors[0], "app_id": app_id, "majors": majors,
            "location": f"apps/{app_id}", "state": state}


def _promoted_record(app_id, major):
    return {"_major": major, "app_id": app_id, "verdict": "PROMOTED", "major": major}


def _entry(app_id, path=f"__PATH__", **kw):
    e = {"id": app_id, "name": app_id, "description": "x", "status": "beta"}
    if path == "__PATH__":
        e["path"] = f"apps/{app_id}"
    elif path is not None:
        e["path"] = path
    e.update(kw)
    return e


# ── the matching case for each of the three shapes ────────────────────────────

def test_matching_playground_entry_passes(tmp_path, monkeypatch):
    repo = _build_repo(tmp_path, stored=[_stored_record("foo", ["python"], "building")])
    monkeypatch.setattr(catalog_lint, "REPO", repo)
    apps = [_entry("foo", tier="playground", majors=["python"], state="building")]
    errors, _ = catalog_lint.lint_generated_fields(apps)
    assert errors == []


def test_matching_pending_entry_passes(tmp_path, monkeypatch):
    repo = _build_repo(tmp_path, pending=[{"app_id": "foo", "reason": "x", "blocked_on": "y"}])
    monkeypatch.setattr(catalog_lint, "REPO", repo)
    apps = [_entry("foo", tier="playground")]
    errors, _ = catalog_lint.lint_generated_fields(apps)
    assert errors == []


def test_matching_promoted_entry_passes(tmp_path, monkeypatch):
    repo = _build_repo(tmp_path, promoted=[_promoted_record("foo", "python")])
    monkeypatch.setattr(catalog_lint, "REPO", repo)
    apps = [_entry("foo", tier="promoted", majors=["python"])]
    errors, _ = catalog_lint.lint_generated_fields(apps)
    assert errors == []


# ── drift between the catalog and the record ──────────────────────────────────

def test_wrong_majors_on_a_stored_entry_fails(tmp_path, monkeypatch):
    repo = _build_repo(tmp_path, stored=[_stored_record("foo", ["python"], "building")])
    monkeypatch.setattr(catalog_lint, "REPO", repo)
    apps = [_entry("foo", tier="playground", majors=["node"], state="building")]
    errors, _ = catalog_lint.lint_generated_fields(apps)
    assert any("majors" in e and "foo" in e for e in errors)


def test_wrong_state_on_a_stored_entry_fails(tmp_path, monkeypatch):
    repo = _build_repo(tmp_path, stored=[_stored_record("foo", ["python"], "building")])
    monkeypatch.setattr(catalog_lint, "REPO", repo)
    apps = [_entry("foo", tier="playground", majors=["python"], state="gated")]
    errors, _ = catalog_lint.lint_generated_fields(apps)
    assert any("state" in e and "foo" in e for e in errors)


def test_wrong_tier_on_a_stored_entry_fails(tmp_path, monkeypatch):
    repo = _build_repo(tmp_path, stored=[_stored_record("foo", ["python"], "building")])
    monkeypatch.setattr(catalog_lint, "REPO", repo)
    apps = [_entry("foo", tier="promoted", majors=["python"], state="building")]
    errors, _ = catalog_lint.lint_generated_fields(apps)
    assert any("tier" in e and "foo" in e for e in errors)


def test_pending_entry_with_wrong_tier_fails(tmp_path, monkeypatch):
    repo = _build_repo(tmp_path, pending=[{"app_id": "foo", "reason": "x", "blocked_on": "y"}])
    monkeypatch.setattr(catalog_lint, "REPO", repo)
    apps = [_entry("foo", tier="promoted")]
    errors, _ = catalog_lint.lint_generated_fields(apps)
    assert any("tier" in e and "foo" in e for e in errors)


def test_promoted_entry_with_wrong_majors_fails(tmp_path, monkeypatch):
    repo = _build_repo(tmp_path, promoted=[_promoted_record("foo", "python")])
    monkeypatch.setattr(catalog_lint, "REPO", repo)
    apps = [_entry("foo", tier="promoted", majors=["node"])]
    errors, _ = catalog_lint.lint_generated_fields(apps)
    assert any("majors" in e and "foo" in e for e in errors)


# ── pending entries don't need majors/state, only the right tier ──────────────

def test_pending_entry_without_majors_or_state_is_fine(tmp_path, monkeypatch):
    """Absence is a value, not a gap: a pending app has no record to check
    majors/state against, and the gate must not demand fields it can't verify."""
    repo = _build_repo(tmp_path, pending=[{"app_id": "foo", "reason": "x", "blocked_on": "y"}])
    monkeypatch.setattr(catalog_lint, "REPO", repo)
    apps = [_entry("foo", tier="playground")]  # no majors, no state key at all
    errors, _ = catalog_lint.lint_generated_fields(apps)
    assert errors == []


# ── out of scope on purpose: archived and pathless entries ────────────────────

def test_archived_entry_is_skipped_regardless_of_content(tmp_path, monkeypatch):
    repo = _build_repo(tmp_path)
    monkeypatch.setattr(catalog_lint, "REPO", repo)
    apps = [_entry("foo", status="archived", tier="nonsense", majors="not-a-list")]
    errors, _ = catalog_lint.lint_generated_fields(apps)
    assert errors == []


def test_pathless_entry_is_skipped_regardless_of_content(tmp_path, monkeypatch):
    """Loose external repos like grove/willow-grove: no apps/ dir, no keeping
    record by P1's own scope, so P3 has nothing to check them against either —
    same open question docs/store_refit_plan.md already names, not P3's to
    resolve."""
    repo = _build_repo(tmp_path)
    monkeypatch.setattr(catalog_lint, "REPO", repo)
    apps = [_entry("foo", path=None, tier="nonsense")]
    errors, _ = catalog_lint.lint_generated_fields(apps)
    assert errors == []


# ── the unreachable branch, exercised directly ─────────────────────────────────

def test_entry_with_no_record_anywhere_errors_loudly(tmp_path, monkeypatch):
    """Should never happen if lint_records() ran first (P1 guarantees every
    apps/ dir has a record or a pending entry) — but this function takes the
    apps list directly, so it's tested standalone rather than assumed safe."""
    repo = _build_repo(tmp_path)
    monkeypatch.setattr(catalog_lint, "REPO", repo)
    apps = [_entry("foo", tier="playground")]
    errors, _ = catalog_lint.lint_generated_fields(apps)
    assert any("no keeping record" in e for e in errors)
