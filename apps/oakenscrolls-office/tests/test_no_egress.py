"""The no-egress zone is structural, not policy (utety pattern): the ledger and
the math must be incapable of talking to anything.

The AST scan now lives in the shared ``safe-app-common`` package (convention
#13); this file declares only oakenscrolls' core partition and calls the shared
assertions.

CORE (no-egress): office_db.py, office_paths.py, calibration.py, almanac_seam.py.

Requires ``safe-app-common`` (pyproject [project.optional-dependencies].test):
    pip install -e .[test]
"""
from pathlib import Path

from safe_app_common.no_egress import assert_does_not_import, assert_no_egress

ROOT = Path(__file__).resolve().parent.parent
NO_EGRESS_MODULES = ("office_db.py", "office_paths.py", "calibration.py", "almanac_seam.py")


def test_core_modules_cannot_egress():
    assert_no_egress(ROOT, NO_EGRESS_MODULES)


def test_core_does_not_import_the_bridge():
    # The Willow seam points OUTWARD only: bridge imports core, never reverse.
    assert_does_not_import(ROOT, NO_EGRESS_MODULES, {"willow_bridge"})
