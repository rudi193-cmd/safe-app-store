"""PaperAdapter fills locally + is idempotent; LiveAdapter.place_order ALWAYS
raises LiveTradingDisabled."""
import pytest

from njord.execution.adapter import PaperAdapter, LiveAdapter, LiveTradingDisabled
from njord.execution.idempotency import IdempotencyStore, client_order_id
from njord.risk.gate import LiveGate


def test_paper_adapter_fills_locally():
    adapter = PaperAdapter()
    fill = adapter.place_order("AAPL", "buy", 10, 150.0)
    assert fill.simulated is True
    assert fill.filled_qty == 10
    assert fill.fill_price == 150.0
    assert fill.order.client_id.startswith("njord-")


def test_paper_adapter_is_idempotent():
    store = IdempotencyStore()
    adapter = PaperAdapter(store)
    f1 = adapter.place_order("AAPL", "buy", 10, 150.0, session="s1")
    f2 = adapter.place_order("AAPL", "buy", 10, 150.0, session="s1")  # same order
    # Same client id, ONE order — the second call returns the original fill.
    assert f1.order.client_id == f2.order.client_id
    assert f1 is f2
    assert len(store._seen) == 1


def test_different_orders_get_different_ids():
    assert client_order_id("AAPL", "buy", 10) != client_order_id("AAPL", "buy", 11)
    assert client_order_id("AAPL", "buy", 10) != client_order_id("MSFT", "buy", 10)


def test_live_adapter_always_raises():
    adapter = LiveAdapter()
    with pytest.raises(LiveTradingDisabled):
        adapter.place_order("AAPL", "buy", 1, 100.0)


def test_live_adapter_raises_even_if_gate_were_cleared(monkeypatch):
    # Force a "cleared" gate; the LiveAdapter must STILL refuse (hard stop).
    monkeypatch.setenv("NJORD_LIVE_CREDENTIAL", "key")
    monkeypatch.setenv("NJORD_I_UNDERSTAND_LIVE", "I-UNDERSTAND-LIVE")
    gate = LiveGate()
    adapter = LiveAdapter(gate)
    with pytest.raises(LiveTradingDisabled):
        adapter.place_order("AAPL", "buy", 1, 100.0, paper_fills=9999, paper_days=9999)


def test_reconcile_stub_reports_no_discrepancy():
    store = IdempotencyStore()
    store.record("njord-abc", {"symbol": "AAPL"})
    rep = store.reconcile(broker_open_orders=[])
    assert rep["reconciled"] is True
    assert rep["discrepancies"] == []
