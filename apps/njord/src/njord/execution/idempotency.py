"""idempotency.py — client-ID'd order keys + a reconcile() stub.

A crash-and-restart must never double-submit. Every order carries a
deterministic client_order_id derived from its business content; the
IdempotencyStore remembers which client_ids have been seen, so submitting the
same logical order twice yields ONE order.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field


def client_order_id(symbol: str, side: str, qty: int, session: str = "default") -> str:
    """Deterministic client order id from the order's business content.

    Same (symbol, side, qty, session) -> same id, so a retry is recognised as a
    duplicate rather than a new order.
    """
    raw = f"{session}:{symbol.upper()}:{side.lower()}:{int(qty)}"
    return "njord-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


@dataclass
class IdempotencyStore:
    """In-memory (or caller-persisted) set of seen client_order_ids."""
    _seen: dict[str, dict] = field(default_factory=dict)

    def seen(self, client_id: str) -> bool:
        return client_id in self._seen

    def record(self, client_id: str, payload: dict) -> None:
        # First write wins; a duplicate never overwrites the original order.
        self._seen.setdefault(client_id, payload)

    def get(self, client_id: str) -> dict | None:
        return self._seen.get(client_id)

    def reconcile(self, broker_open_orders: list[dict] | None = None) -> dict:
        """STUB: on startup, compare local seen-orders to actual broker state.

        A real reconcile pulls the broker's open orders + positions and refuses
        to trade if they disagree with local state. In this recommend-only build
        there is no broker, so this returns a benign, no-discrepancy report.
        """
        broker_open_orders = broker_open_orders or []
        return {
            "reconciled": True,
            "local_known": len(self._seen),
            "broker_open": len(broker_open_orders),
            "discrepancies": [],
            "note": "stub reconcile — no broker wired in recommend-only build",
        }
