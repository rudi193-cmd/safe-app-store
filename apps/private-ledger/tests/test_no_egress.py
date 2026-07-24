"""The no-egress zone is structural, not policy (oakenscrolls pattern): the
ledger and the math must be incapable of talking to anything.

The AST scan itself now lives in the shared ``safe-app-common`` package
(convention #13) — this file declares only private-ledger's own core/seam
partition and calls the shared assertions, so every app enforces the invariant
from one canonical checker instead of a per-app copy.

CORE (no-egress): db.py, schema.py, pl_paths.py, subscriptions.py.
OUTWARD (excluded): web.py, app.py, llm.py, serve.py, willow_bridge.py.

Requires ``safe-app-common`` (see pyproject [project.optional-dependencies].test):
    pip install -e .[test]
"""
from pathlib import Path

from safe_app_common.no_egress import (
    assert_does_not_import,
    assert_file_no_egress,
    assert_no_egress,
)

CORE = Path(__file__).resolve().parent.parent / "src" / "private_ledger"
NO_EGRESS_MODULES = ("db.py", "schema.py", "pl_paths.py", "subscriptions.py")


def test_core_modules_cannot_egress():
    assert_no_egress(CORE, NO_EGRESS_MODULES)


def test_core_does_not_import_the_web_seam():
    # The seam points OUTWARD only: web imports core, never the reverse.
    assert_does_not_import(CORE, NO_EGRESS_MODULES, {"web"})


def test_core_does_not_import_the_willow_bridge():
    # The Willow seam points OUTWARD only: bridge imports core, never reverse.
    assert_does_not_import(CORE, NO_EGRESS_MODULES, {"willow_bridge"})


def test_core_does_not_import_the_serve_seam():
    # The stdio seam points OUTWARD only: serve imports the core, never reverse.
    assert_does_not_import(CORE, NO_EGRESS_MODULES, {"serve"})


def test_serve_seam_is_stdio_only():
    # serve.py is OUTWARD (not in the core set) but must still never phone home:
    # it is a stdio command loop, reaching the world only through stdin/stdout.
    assert_file_no_egress(CORE / "serve.py")


def test_willow_bridge_is_pure_injection():
    # willow_bridge is OUTWARD but must still never phone home: no ``import
    # willow`` and no network/process import. It reaches Willow only through an
    # INJECTED ingest callable.
    assert_file_no_egress(CORE / "willow_bridge.py", also_ban={"willow"})
