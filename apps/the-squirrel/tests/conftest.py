"""
Test env: every test runs against its own throwaway box — SQLite db, gate
ledger, receipt log, vault, settings all under tmp_path. No Willow, no
Postgres, no fakes: the vendored lattice constants and the SQLite backend
are the product's own zero-dependency path. (Postgres-specific behavior is
exercised by setting SQUIRREL_BACKEND=postgres against a real server.)
"""
import pytest


@pytest.fixture(autouse=True)
def squirrel_box(tmp_path, monkeypatch):
    """Every test runs as the journal actor against a throwaway box.

    Tests that exercise gate policy itself (tests/test_gate.py) override the
    actor inside the test body.
    """
    monkeypatch.setenv("SQUIRREL_HOME", str(tmp_path / "box"))
    monkeypatch.setenv("SQUIRREL_DB", str(tmp_path / "box" / "squirrel.db"))
    monkeypatch.setenv("SQUIRREL_GATE_DIR", str(tmp_path / "willowgate"))
    monkeypatch.setenv("SQUIRREL_RECEIPT_DB", str(tmp_path / "receipts.db"))
    monkeypatch.setenv("SQUIRREL_GAPS_DB", str(tmp_path / "gaps.db"))
    monkeypatch.setenv("SQUIRREL_SKIP_SEED", "1")  # 779 rows only where a test asks
    monkeypatch.delenv("SQUIRREL_BACKEND", raising=False)
    monkeypatch.delenv("WILLOW_DB_URL", raising=False)
    import sap.core.gate as gate
    import sap.core.receipts as receipts
    import sap.core.gaps as gaps
    gate.close()      # drop any backend built against a previous tmp dir
    receipts.reset()  # re-point the receipt log at this test's tmp db
    gaps.reset()      # re-point the gap ledger at this test's tmp db
    try:
        with gate.actor("journal"):
            yield
    finally:
        gate.close()
        receipts.reset()
        gaps.reset()
