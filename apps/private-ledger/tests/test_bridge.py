# b17: PLBRDG-T  ΔΣ=42
"""Bridge tests (mirror oakenscrolls-office tests/test_bridge.py).

Runs WITHOUT textual: imports only the bridge and the pure core
(db / schema / subscriptions). No TUI, no network.
"""
import sys
from datetime import date
from pathlib import Path

import pytest

# Make the packaged core importable as ``private_ledger`` without installing.
SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

from private_ledger import schema  # noqa: E402
from private_ledger.db import LedgerDB  # noqa: E402
from private_ledger import willow_bridge as bridge  # noqa: E402

TODAY = date(2026, 7, 15)
LEAK_TOKEN = "ZZUNIQUELEAKTOKEN42"


@pytest.fixture()
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("WILLOW_HOME", str(tmp_path / "willow"))
    db_path = str(tmp_path / "ledger.db")
    schema.init_ledger(db_path)
    ledger = LedgerDB(db_path)
    acct = 1
    ledger.add_account("Checking", "checking", 0.0)

    # One inflow, one outflow carrying a UNIQUE raw description token, and a
    # monthly recurring charge (3 occurrences) so a subscription is detected.
    ledger.add_transaction(acct, "2026-07-02", 4000.00, "Payroll", "Income")
    ledger.add_transaction(acct, "2026-07-05", -87.31, LEAK_TOKEN, "Shopping")
    for d in ("2026-05-10", "2026-06-10", "2026-07-10"):
        ledger.add_transaction(acct, d, -15.99, "NETFLIX", "Entertainment")
    return ledger


def test_build_summary_atom_is_aggregate_only(db):
    atom = bridge.build_summary_atom(db, today=TODAY)
    assert set(atom) >= {"content", "domain", "source", "tags"}
    assert atom["domain"] == "saps1"
    assert atom["source"] == "private-ledger"
    # The raw description token must NOT leak into any part of the atom.
    blob = repr(atom)
    assert LEAK_TOKEN not in blob
    # Aggregates are present.
    assert "2026-07" in atom["content"]
    assert "income" in atom["content"] and "spend" in atom["content"]
    assert "Active subscriptions: 1" in atom["content"]


def test_promote_summary_no_ingest_returns_unsent(db):
    atom = bridge.promote_summary(db, today=TODAY)
    assert "stored" not in atom
    assert atom["source"] == "private-ledger"


def test_promote_summary_injects_once_and_succeeds(db):
    sent = []

    def ingest(a):  # loud contract: return a confirmation
        sent.append(a)
        return {"id": "atom-1"}

    atom = bridge.promote_summary(db, today=TODAY, ingest=ingest)
    assert len(sent) == 1
    assert sent[0]["domain"] == "saps1"
    assert atom["stored"] == {"id": "atom-1"}


def test_promote_summary_closes_loudly_on_refused_ingest(db):
    # willow-style error dict -> loud
    with pytest.raises(bridge.PromotionRefused):
        bridge.promote_summary(db, today=TODAY, ingest=lambda a: {"error": "gate denied"})
    # no confirmation (None/falsy) -> loud
    with pytest.raises(bridge.PromotionRefused):
        bridge.promote_summary(db, today=TODAY, ingest=lambda a: None)
    # a raising ingest -> loud
    with pytest.raises(bridge.PromotionRefused):
        def boom(a):
            raise RuntimeError("kb offline")
        bridge.promote_summary(db, today=TODAY, ingest=boom)


def test_surface_due_off_by_default(db, monkeypatch):
    monkeypatch.delenv("PRIVATE_LEDGER_PROACTIVE", raising=False)
    assert bridge.surface_due(db, today=TODAY) is False
    assert not bridge.signal_path().exists()


def test_surface_due_publishes_facts_when_enabled(db, monkeypatch):
    monkeypatch.setenv("PRIVATE_LEDGER_PROACTIVE", "1")
    # Netflix last charged 2026-07-10, monthly -> next ~2026-08-09; widen window.
    published = bridge.surface_due(db, today=TODAY, lead_days=40)
    assert published is True
    import json
    payload = json.loads(bridge.signal_path().read_text())
    assert payload["app_id"] == "private-ledger"
    entry = payload["due"][0]
    # Facts only: merchant token, next_expected, amount, annualized. No raw desc.
    assert set(entry) == {"merchant", "next_expected", "amount", "annualized"}
    assert entry["merchant"] == "netflix"
    assert LEAK_TOKEN not in json.dumps(payload)
