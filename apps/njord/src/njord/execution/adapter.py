"""adapter.py — execution adapters.

  - ExecutionAdapter: the interface.
  - PaperAdapter: SIMULATES fills locally. No network. Idempotent by client id
    (submitting the same client-id twice yields ONE order/fill).
  - LiveAdapter: place_order() ALWAYS raises LiveTradingDisabled in this build.
    No broker is wired. Even when one eventually is, place_order() must first
    check gate.is_live_authorized() and refuse if it is not cleared.

SAFETY INVARIANT #1: no code path here places a real order. The LiveAdapter is a
hard stop, not a TODO.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

from ..risk.gate import LiveGate
from .idempotency import IdempotencyStore, client_order_id


class LiveTradingDisabled(RuntimeError):
    """Raised by LiveAdapter to guarantee no real order is ever placed."""


@dataclass(frozen=True)
class Order:
    symbol: str
    side: str          # "buy" or "sell"
    qty: int
    price: float
    client_id: str

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "qty": self.qty,
            "price": self.price,
            "client_id": self.client_id,
        }


@dataclass(frozen=True)
class Fill:
    order: Order
    filled_qty: int
    fill_price: float
    ts: str
    simulated: bool

    def to_dict(self) -> dict:
        return {
            "order": self.order.to_dict(),
            "filled_qty": self.filled_qty,
            "fill_price": self.fill_price,
            "ts": self.ts,
            "simulated": self.simulated,
        }


class ExecutionAdapter(Protocol):
    mode: str

    def place_order(self, symbol: str, side: str, qty: int, price: float,
                    session: str = "default") -> Fill: ...


class PaperAdapter:
    """Simulates fills locally. No network. Idempotent by client_order_id."""

    mode = "paper"

    def __init__(self, store: IdempotencyStore | None = None) -> None:
        self._store = store or IdempotencyStore()
        self._fills: dict[str, Fill] = {}

    def place_order(self, symbol: str, side: str, qty: int, price: float,
                    session: str = "default") -> Fill:
        cid = client_order_id(symbol, side, qty, session)
        if self._store.seen(cid):
            # Duplicate submission -> return the original fill, do NOT create a
            # second order.
            return self._fills[cid]

        fill = Fill(
            order=Order(symbol.upper(), side.lower(), int(qty), float(price), cid),
            filled_qty=int(qty),
            fill_price=float(price),          # simple model: fill at the given price
            ts=datetime.now(timezone.utc).isoformat(),
            simulated=True,
        )
        self._store.record(cid, fill.to_dict())
        self._fills[cid] = fill
        return fill

    def open_order_count(self) -> int:
        return 0  # paper fills are immediate in this simple model


class LiveAdapter:
    """LIVE IS DISABLED. place_order ALWAYS raises. No broker is wired.

    The gate check is present so that the ONLY way this class could ever place an
    order — in some future build that actually wires a broker — is behind a
    cleared paper-first gate. In THIS build the final `raise` is unconditional.
    """

    mode = "live"

    def __init__(self, gate: LiveGate | None = None) -> None:
        self._gate = gate or LiveGate()

    def place_order(self, symbol: str, side: str, qty: int, price: float,
                    session: str = "default", paper_fills: int = 0,
                    paper_days: int = 0) -> Fill:
        # Even if a broker were wired, refuse unless the gate is cleared.
        if not self._gate.is_live_authorized(paper_fills, paper_days):
            raise LiveTradingDisabled(
                "live trading is not authorized: paper-first gate is not cleared"
            )
        # HARD STOP: this build wires no broker and never places a real order.
        raise LiveTradingDisabled(
            "live trading is disabled in this build — no broker is wired and no "
            "code path places a real order (recommend-only)"
        )
