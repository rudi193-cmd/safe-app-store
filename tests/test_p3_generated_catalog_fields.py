"""Tests for the store refit's P3 gate, extended by the status-vocabulary
migration: catalog_lint.py's lint_generated_fields().

Same shape as tests/test_p1_keeping_records.py: a synthetic stores/ tree under
tmp_path, catalog.json's "apps" list passed in directly (this function takes
it as an argument rather than reading a file, so no catalog.json fixture is
needed), and catalog_lint.REPO monkeypatched so stores/pending.json and the
records are read from the synthetic tree.

Since the status-vocabulary migration, a catalog entry has no separate
`state` field — `status` carries a stored entry's record-state value
directly. `_stored_record()` still uses `state`, because that's a keeping
record's own field (stores/{major}/stored/<id>.json, from P1) and is
unaffected by this migration; only the *catalog* representation changed.
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
    """A P1 keeping record — untouched by the status-vocabulary migration."""
    return {"_major": major or majors[0], "app_id": app_id, "majors": majors,
            "location": f"apps/{app_id}", "state": state}


def _promoted_record(app_id, major):
    return {"_major": major, "app_id": app_id, "verdict": "PROMOTED", "major": major}


def _entry(app_id, path="__PATH__", status="building", **kw):
    e = {"id": app_id, "name": app_id, "description": "x", "status": status}
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
    apps = [_entry("foo", tier="playground", majors=["python"], status="building")]
    errors, _ = catalog_lint.lint_generated_fields(apps)
    assert errors == []


def test_matching_pending_entry_passes(tmp_path, monkeypatch):
    """A pending entry's status is manual, not generated — any valid status
    passes, since there's no record to check it against."""
    repo = _build_repo(tmp_path, pending=[{"app_id": "foo", "reason": "x", "blocked_on": "y"}])
    monkeypatch.setattr(catalog_lint, "REPO", repo)
    apps = [_entry("foo", tier="playground", status="gated")]
    errors, _ = catalog_lint.lint_generated_fields(apps)
    assert errors == []


def test_matching_promoted_entry_passes(tmp_path, monkeypatch):
    """A promoted entry's status is likewise manual — no promoted record
    carries a state-shaped field to check it against."""
    repo = _build_repo(tmp_path, promoted=[_promoted_record("foo", "python")])
    monkeypatch.setattr(catalog_lint, "REPO", repo)
    apps = [_entry("foo", tier="promoted", majors=["python"], status="gated")]
    errors, _ = catalog_lint.lint_generated_fields(apps)
    assert errors == []


# ── drift between the catalog and the record ──────────────────────────────────

def test_wrong_majors_on_a_stored_entry_fails(tmp_path, monkeypatch):
    repo = _build_repo(tmp_path, stored=[_stored_record("foo", ["python"], "building")])
    monkeypatch.setattr(catalog_lint, "REPO", repo)
    apps = [_entry("foo", tier="playground", majors=["node"], status="building")]
    errors, _ = catalog_lint.lint_generated_fields(apps)
    assert any("majors" in e and "foo" in e for e in errors)


def test_wrong_status_on_a_stored_entry_fails(tmp_path, monkeypatch):
    """The migrated check: catalog status must equal the record's state."""
    repo = _build_repo(tmp_path, stored=[_stored_record("foo", ["python"], "building")])
    monkeypatch.setattr(catalog_lint, "REPO", repo)
    apps = [_entry("foo", tier="playground", majors=["python"], status="gated")]
    errors, _ = catalog_lint.lint_generated_fields(apps)
    assert any("status" in e and "foo" in e for e in errors)


def test_wrong_tier_on_a_stored_entry_fails(tmp_path, monkeypatch):
    repo = _build_repo(tmp_path, stored=[_stored_record("foo", ["python"], "building")])
    monkeypatch.setattr(catalog_lint, "REPO", repo)
    apps = [_entry("foo", tier="promoted", majors=["python"], status="building")]
    errors, _ = catalog_lint.lint_generated_fields(apps)
    assert any("tier" in e and "foo" in e for e in errors)


def test_pending_entry_with_wrong_tier_fails(tmp_path, monkeypatch):
    repo = _build_repo(tmp_path, pending=[{"app_id": "foo", "reason": "x", "blocked_on": "y"}])
    monkeypatch.setattr(catalog_lint, "REPO", repo)
    apps = [_entry("foo", tier="promoted", status="building")]
    errors, _ = catalog_lint.lint_generated_fields(apps)
    assert any("tier" in e and "foo" in e for e in errors)


def test_promoted_entry_with_wrong_majors_fails(tmp_path, monkeypatch):
    repo = _build_repo(tmp_path, promoted=[_promoted_record("foo", "python")])
    monkeypatch.setattr(catalog_lint, "REPO", repo)
    apps = [_entry("foo", tier="promoted", majors=["node"], status="building")]
    errors, _ = catalog_lint.lint_generated_fields(apps)
    assert any("majors" in e and "foo" in e for e in errors)


# ── the status-vocabulary migration's own guard ────────────────────────────────

def test_leftover_separate_state_field_fails(tmp_path, monkeypatch):
    """A catalog entry must not carry both status and a separate state key —
    that's the exact two-fields-for-one-fact shape the migration closed."""
    repo = _build_repo(tmp_path, stored=[_stored_record("foo", ["python"], "building")])
    monkeypatch.setattr(catalog_lint, "REPO", repo)
    apps = [_entry("foo", tier="playground", majors=["python"], status="building",
                    state="building")]
    errors, _ = catalog_lint.lint_generated_fields(apps)
    assert any("state" in e and "foo" in e for e in errors)


def test_pending_entry_status_can_differ_from_any_hypothetical_state(tmp_path, monkeypatch):
    """Not generated, so nothing to disagree with: a pending entry's manually
    set status is never compared against anything, unlike a stored entry's."""
    repo = _build_repo(tmp_path, pending=[{"app_id": "foo", "reason": "x", "blocked_on": "y"}])
    monkeypatch.setattr(catalog_lint, "REPO", repo)
    for status in ("seeded", "building", "gated", "stalled"):
        apps = [_entry("foo", tier="playground", status=status)]
        errors, _ = catalog_lint.lint_generated_fields(apps)
        assert errors == [], f"status={status!r} should not be flagged"


# ── which store a stored record's majors are checked against ──────────────────

def test_declared_major_is_honoured(tmp_path, monkeypatch):
    repo = _build_repo(tmp_path, stored=[_stored_record("foo", ["node"], "building", major="node")])
    monkeypatch.setattr(catalog_lint, "REPO", repo)
    apps = [_entry("foo", tier="playground", majors=["node"], status="building")]
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
    apps = [_entry("foo", path=None, tier="nonsense", status="building")]
    errors, _ = catalog_lint.lint_generated_fields(apps)
    assert errors == []


# ── the unreachable branch, exercised directly ─────────────────────────────────

def test_entry_with_no_record_anywhere_errors_loudly(tmp_path, monkeypatch):
    """Should never happen if lint_records() ran first (P1 guarantees every
    apps/ dir has a record or a pending entry) — but this function takes the
    apps list directly, so it's tested standalone rather than assumed safe."""
    repo = _build_repo(tmp_path)
    monkeypatch.setattr(catalog_lint, "REPO", repo)
    apps = [_entry("foo", tier="playground", status="building")]
    errors, _ = catalog_lint.lint_generated_fields(apps)
    assert any("no keeping record" in e for e in errors)
