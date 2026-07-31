"""P3 (docs/store_refit_plan.md, rule 9): the real catalog lives in
.willow/store/catalog.json. The root catalog.json is a pointer left for
anything that still looks at the repo root — it must never become a second
copy of the data, or the store is back to keeping two things that can drift.

Stdlib only.
"""
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def test_root_catalog_is_a_pointer_not_a_second_copy():
    root = json.loads((REPO / "catalog.json").read_text())
    assert root.get("$pointer") == ".willow/store/catalog.json", (
        "root catalog.json must point at .willow/store/catalog.json"
    )
    assert "apps" not in root, (
        "root catalog.json has an 'apps' list — it has become a second copy "
        "of the real catalog instead of a pointer, which is exactly the "
        "duplicated-stock problem the store refit exists to avoid"
    )


def test_willow_store_catalog_is_the_real_one():
    real = json.loads((REPO / ".willow" / "store" / "catalog.json").read_text())
    assert isinstance(real.get("apps"), list) and len(real["apps"]) > 0, (
        ".willow/store/catalog.json should hold the real, non-empty apps list"
    )


def test_catalog_lint_reads_the_new_location():
    src = (REPO / "tools" / "catalog_lint.py").read_text()
    assert '".willow" / "store" / "catalog.json"' in src, (
        "catalog_lint.py must read the catalog from .willow/store/, not the "
        "root pointer — otherwise --strict would validate the pointer "
        "stub instead of the real data and pass vacuously"
    )


def test_tui_reads_the_new_location():
    src = (REPO / "tui.py").read_text()
    assert '".willow" / "store" / "catalog.json"' in src, (
        "tui.py must read the catalog from .willow/store/, not the root pointer"
    )
