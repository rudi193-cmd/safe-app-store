"""P4 (docs/store_refit_plan.md): catalog.json's top-level keys are a closed
set (version, store, description, apps). discovery_sources — a curated
directory of third-party hosted tools, never kept, provisioned, or promoted —
moved to docs/discovery_sources.md because the catalog is the shelf's stock,
not its market research. This proves the gate that keeps a new organ like it
from growing back in silently: an unknown top-level key must fail, not warn.

Stdlib only.
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


def _minimal_repo(tmp_path, extra_top_level=None):
    """A single seeded app (no manifest needed), fully satisfying P1/P3, so
    only the top-level-key check under test can produce a finding."""
    (tmp_path / "apps" / "foo").mkdir(parents=True)

    stores = tmp_path / "stores"
    (stores / "python" / "stored").mkdir(parents=True)
    (stores / "python" / "promoted").mkdir(parents=True)
    record = {"app_id": "foo", "majors": ["python"], "location": "apps/foo",
              "state": "seeded"}
    (stores / "python" / "stored" / "foo.json").write_text(json.dumps(record))

    catalog_dir = tmp_path / ".willow" / "store"
    catalog_dir.mkdir(parents=True)
    catalog = {
        "version": "1.0",
        "store": "SAFE App Store",
        "description": "test fixture",
        "apps": [{
            "id": "foo", "name": "foo", "description": "x", "status": "seeded",
            "path": "apps/foo", "tier": "playground", "majors": ["python"],
        }],
    }
    if extra_top_level:
        catalog.update(extra_top_level)
    catalog_dir.joinpath("catalog.json").write_text(json.dumps(catalog, indent=2))
    return tmp_path


def test_known_top_level_keys_are_accepted(tmp_path, monkeypatch):
    repo = _minimal_repo(tmp_path)
    monkeypatch.setattr(catalog_lint, "REPO", repo)
    errors, _ = catalog_lint.lint()
    assert not any("unknown top-level key" in e for e in errors), errors


def test_discovery_sources_growing_back_is_rejected(tmp_path, monkeypatch):
    repo = _minimal_repo(tmp_path, {"discovery_sources": [{"id": "x"}]})
    monkeypatch.setattr(catalog_lint, "REPO", repo)
    errors, _ = catalog_lint.lint()
    assert any(
        "unknown top-level key" in e and "'discovery_sources'" in e
        for e in errors
    ), errors


def test_an_arbitrary_unknown_key_is_rejected(tmp_path, monkeypatch):
    repo = _minimal_repo(tmp_path, {"some_new_organ": {}})
    monkeypatch.setattr(catalog_lint, "REPO", repo)
    errors, _ = catalog_lint.lint()
    assert any(
        "unknown top-level key" in e and "'some_new_organ'" in e
        for e in errors
    ), errors
