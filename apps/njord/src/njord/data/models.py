"""models.py — data primitives that CARRY provenance.

Every datapoint that flows through Njord knows where it came from (source_id)
and when it was fetched (fetched_at). A Bar/Quote without provenance cannot be
constructed — provenance is a required field, not an afterthought.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Provenance:
    """Where a datapoint came from and when.

    source_id must correspond to a Source registered in the SourceRegistry;
    the registry is what enforces "verified & public sources only".
    """
    source_id: str
    fetched_at: str = field(default_factory=_utc_now_iso)
    # Optional pointer to the authoritative record (URL, accession no, series id).
    reference: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Bar:
    """An OHLCV bar with attached provenance."""
    symbol: str
    ts: str                 # ISO date/datetime of the bar
    open: float
    high: float
    low: float
    close: float
    volume: float
    provenance: Provenance

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


@dataclass(frozen=True)
class Quote:
    """A point-in-time quote with attached provenance."""
    symbol: str
    ts: str
    bid: float
    ask: float
    last: float
    provenance: Provenance

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0

    def to_dict(self) -> dict:
        return asdict(self)
