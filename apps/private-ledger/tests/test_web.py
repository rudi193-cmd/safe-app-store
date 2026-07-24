"""Web mirror — pure router, no socket. Runs WITHOUT textual.

Imports only web / db / schema. handle() is called directly.
"""
import json
import sys
from datetime import date
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

import pytest  # noqa: E402

from private_ledger import web  # noqa: E402
from private_ledger.db import LedgerDB  # noqa: E402
from private_ledger.schema import init_ledger  # noqa: E402

TODAY = date(2026, 7, 24)


@pytest.fixture()
def db(tmp_path):
    db_path = str(tmp_path / "ledger.db")
    init_ledger(db_path)
    ledger = LedgerDB(db_path)
    ledger.add_account("Checking", "checking", 1000.0)
    accounts = ledger.get_accounts()
    acct_id = accounts[0]["id"]
    for m in range(1, 7):
        ledger.add_transaction(acct_id, f"2026-0{m}-05", -9.99,
                               "NETFLIX #1234", "Entertainment")
    ledger.add_transaction(acct_id, "2026-06-01", 2500.0,
                           "PAYROLL DEPOSIT", "Income")
    return ledger


def test_root_is_html(db):
    status, ctype, body = web.handle("GET", "/", db, TODAY)
    assert status == 200
    assert "text/html" in ctype
    assert "Private Ledger" in body
    assert "NETFLIX #1234" in body  # known description present
    assert "$" in body               # a balance rendered
    assert "<svg" in body            # cash-flow chart drawn


def test_data_json_parses(db):
    status, ctype, body = web.handle("GET", "/data.json", db, TODAY)
    assert status == 200
    assert ctype == "application/json"
    data = json.loads(body)
    assert "accounts" in data
    assert "transactions" in data
    assert "subscriptions" in data
    assert data["accounts"][0]["name"] == "Checking"


def test_subscriptions_json(db):
    status, ctype, body = web.handle("GET", "/subscriptions.json", db, TODAY)
    assert status == 200
    subs = json.loads(body)
    assert any(s["normalized_merchant"] == "netflix" for s in subs)


def test_post_not_allowed(db):
    assert web.handle("POST", "/", db, TODAY)[0] == 405


def test_unknown_path_404(db):
    assert web.handle("GET", "/nope", db, TODAY)[0] == 404


def test_handle_is_read_only(db):
    before = len(db.get_transactions(limit=999))
    web.handle("GET", "/", db, TODAY)
    web.handle("GET", "/data.json", db, TODAY)
    assert len(db.get_transactions(limit=999)) == before
