"""Serve seam — pure dispatch + stdio loop. Runs WITHOUT textual.

Imports only serve / db / schema / subscriptions / willow_bridge. dispatch() is
called directly; the loop is driven over io.StringIO. No sockets, no TUI.
"""
import io
import json
import sys
from datetime import date
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

import pytest  # noqa: E402

from private_ledger import serve  # noqa: E402
from private_ledger.db import LedgerDB  # noqa: E402
from private_ledger.schema import init_ledger  # noqa: E402

TODAY = date(2026, 7, 24)


@pytest.fixture()
def db(tmp_path):
    db_path = str(tmp_path / "ledger.db")
    init_ledger(db_path)
    ledger = LedgerDB(db_path)
    ledger.add_account("Checking", "checking", 1000.0)
    acct_id = ledger.get_accounts()[0]["id"]
    # Six monthly Netflix charges -> a detectable subscription.
    for m in range(1, 7):
        ledger.add_transaction(acct_id, f"2026-0{m}-05", -9.99,
                               "NETFLIX #1234", "Entertainment")
    ledger.add_transaction(acct_id, "2026-06-01", 2500.0,
                           "PAYROLL DEPOSIT", "Income")
    return ledger


def _tx_count(db) -> int:
    return len(db.get_transactions(limit=1_000_000))


# ── Reads ─────────────────────────────────────────────────────────────────────

def test_ping(db):
    resp = serve.dispatch({"op": "ping"}, db, TODAY, allow_write=False)
    assert resp["ok"] is True
    assert resp["result"] == {"app": "private-ledger", "write_enabled": False}
    resp_w = serve.dispatch({"op": "ping"}, db, TODAY, allow_write=True)
    assert resp_w["result"]["write_enabled"] is True


def test_ops_lists_write_flags(db):
    resp = serve.dispatch({"op": "ops"}, db, TODAY, allow_write=False)
    assert resp["ok"] is True
    ops = {o["op"]: o["write"] for o in resp["result"]}
    assert ops["get_balance"] is False
    assert ops["add_transaction"] is True
    assert ops["delete_transaction"] is True


def test_get_balance_total_matches(db):
    resp = serve.dispatch({"op": "get_balance"}, db, TODAY, allow_write=False)
    assert resp["ok"] is True
    # 1000 opening + 6 * -9.99 + 2500 = 3440.06
    expected = 1000.0 + 6 * -9.99 + 2500.0
    assert resp["result"]["total"] == pytest.approx(expected, abs=0.001)
    assert resp["result"]["accounts"][0]["name"] == "Checking"


def test_get_transactions_returns_seeded_row(db):
    resp = serve.dispatch({"op": "get_transactions", "params": {"limit": 50}},
                          db, TODAY, allow_write=False)
    assert resp["ok"] is True
    descriptions = {tx["description"] for tx in resp["result"]}
    assert "NETFLIX #1234" in descriptions
    assert "PAYROLL DEPOSIT" in descriptions


def test_get_budget_defaults_to_today_month(db):
    resp = serve.dispatch({"op": "get_budget"}, db, TODAY, allow_write=False)
    assert resp["ok"] is True
    assert isinstance(resp["result"], dict)


def test_get_subscriptions_shape(db):
    resp = serve.dispatch({"op": "get_subscriptions"}, db, TODAY, allow_write=False)
    assert resp["ok"] is True
    assert any(s["normalized_merchant"] == "netflix" for s in resp["result"])


def test_get_summary_is_aggregate_atom(db):
    resp = serve.dispatch({"op": "get_summary"}, db, TODAY, allow_write=False)
    assert resp["ok"] is True
    atom = resp["result"]
    assert set(atom) >= {"content", "domain", "source", "tags"}
    assert atom["source"] == "private-ledger"


def test_id_is_echoed_back(db):
    resp = serve.dispatch({"id": 42, "op": "ping"}, db, TODAY, allow_write=False)
    assert resp["id"] == 42
    # And on an error response too.
    err = serve.dispatch({"id": "abc", "op": "nope"}, db, TODAY, allow_write=False)
    assert err["id"] == "abc"
    assert err["ok"] is False


def test_id_absent_when_not_provided(db):
    resp = serve.dispatch({"op": "ping"}, db, TODAY, allow_write=False)
    assert "id" not in resp


# ── Write gating ──────────────────────────────────────────────────────────────

def test_write_disabled_leaves_db_unchanged(db):
    before = _tx_count(db)
    resp = serve.dispatch(
        {"op": "add_transaction",
         "params": {"date": "2026-07-20", "amount": -12.0, "description": "Coffee"}},
        db, TODAY, allow_write=False,
    )
    assert resp["ok"] is False
    assert "writes disabled" in resp["error"]
    assert _tx_count(db) == before  # nothing mutated


def test_add_transaction_when_allowed_changes_db(db):
    before = _tx_count(db)
    resp = serve.dispatch(
        {"op": "add_transaction",
         "params": {"date": "2026-07-20", "amount": -12.0,
                    "description": "Coffee", "category": "Food & Dining"}},
        db, TODAY, allow_write=True,
    )
    assert resp["ok"] is True
    assert resp["result"]["added"] is True
    assert _tx_count(db) == before + 1


def test_add_account_when_allowed(db):
    resp = serve.dispatch(
        {"op": "add_account", "params": {"name": "Savings", "balance": 500.0}},
        db, TODAY, allow_write=True,
    )
    assert resp["ok"] is True
    names = {a["name"] for a in db.get_accounts()}
    assert "Savings" in names


def test_delete_transaction_when_allowed(db):
    tx_id = db.get_transactions(limit=1)[0]["id"]
    before = _tx_count(db)
    resp = serve.dispatch(
        {"op": "delete_transaction", "params": {"id": tx_id}},
        db, TODAY, allow_write=True,
    )
    assert resp["ok"] is True
    assert _tx_count(db) == before - 1


# ── Bad input never raises ────────────────────────────────────────────────────

def test_unknown_op_errors(db):
    resp = serve.dispatch({"op": "teleport"}, db, TODAY, allow_write=True)
    assert resp["ok"] is False
    assert "unknown op" in resp["error"]


def test_missing_op_errors(db):
    resp = serve.dispatch({"params": {}}, db, TODAY, allow_write=True)
    assert resp["ok"] is False


def test_non_numeric_amount_errors_no_exception(db):
    before = _tx_count(db)
    resp = serve.dispatch(
        {"op": "add_transaction",
         "params": {"date": "2026-07-20", "amount": "lots", "description": "x"}},
        db, TODAY, allow_write=True,
    )
    assert resp["ok"] is False
    assert "amount" in resp["error"]
    assert _tx_count(db) == before  # rejected before touching the db


def test_missing_params_errors(db):
    resp = serve.dispatch(
        {"op": "add_transaction", "params": {"amount": -5.0}},
        db, TODAY, allow_write=True,
    )
    assert resp["ok"] is False  # missing date/description


def test_non_dict_request_errors(db):
    resp = serve.dispatch(["not", "an", "object"], db, TODAY, allow_write=True)
    assert resp["ok"] is False


# ── stdio loop end-to-end ─────────────────────────────────────────────────────

def test_run_loop_one_response_per_line(db):
    lines = [
        json.dumps({"id": 1, "op": "ping"}),
        json.dumps({"id": 2, "op": "get_balance"}),
        "",                       # blank -> ignored
        "{not valid json",        # malformed -> error response, loop survives
    ]
    stdin = io.StringIO("\n".join(lines) + "\n")
    stdout = io.StringIO()
    serve.run(db=db, allow_write=False, today=TODAY, stdin=stdin, stdout=stdout)

    out_lines = [ln for ln in stdout.getvalue().splitlines() if ln]
    # Two real requests + one malformed line -> three responses; blank ignored.
    assert len(out_lines) == 3
    r1 = json.loads(out_lines[0])
    r2 = json.loads(out_lines[1])
    r3 = json.loads(out_lines[2])
    assert r1["id"] == 1 and r1["ok"] is True
    assert r2["id"] == 2 and r2["ok"] is True
    assert r3["ok"] is False and "malformed" in r3["error"]


def test_run_loop_write_gated(db):
    before = _tx_count(db)
    req = json.dumps({"op": "add_transaction",
                      "params": {"date": "2026-07-20", "amount": -1.0,
                                 "description": "y"}})
    stdout = io.StringIO()
    serve.run(db=db, allow_write=False, today=TODAY,
              stdin=io.StringIO(req + "\n"), stdout=stdout)
    resp = json.loads(stdout.getvalue().strip())
    assert resp["ok"] is False and "writes disabled" in resp["error"]
    assert _tx_count(db) == before
