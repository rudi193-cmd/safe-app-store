"""registry.py — the source registry that makes "verified & public" real.

Every provider registers a Source with an id, the authority behind it
(e.g. YAHOO_FINANCE, SEC_EDGAR, FRED, or STUB for offline synthetic data) and a
trust tier. Every datapoint carries a source_id; before anything is emitted as a
recommendation, its source_id is checked against this registry. A datapoint (or
an idea) that cites no registered source is a bug — the registry raises.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class TrustTier(IntEnum):
    """Higher is more authoritative. STUB is offline synthetic data — usable for
    development and tests, explicitly NOT a basis for real decisions."""
    STUB = 0            # deterministic offline synthetic data
    CONVENIENCE = 1     # convenient but not system-of-record (e.g. yfinance)
    EXCHANGE = 2        # exchange/broker market data
    PRIMARY = 3         # primary regulatory source (SEC EDGAR, FRED)


@dataclass(frozen=True)
class Source:
    id: str             # stable identifier used as Provenance.source_id
    authority: str      # e.g. "YAHOO_FINANCE", "STUB", "SEC_EDGAR"
    trust: TrustTier
    description: str = ""
    public: bool = True


class UnregisteredSourceError(ValueError):
    """Raised when a datapoint/idea references a source not in the registry."""


class SourceRegistry:
    def __init__(self) -> None:
        self._sources: dict[str, Source] = {}

    def register(self, source: Source) -> Source:
        if source.id in self._sources:
            raise ValueError(f"source already registered: {source.id!r}")
        self._sources[source.id] = source
        return source

    def get(self, source_id: str) -> Source:
        try:
            return self._sources[source_id]
        except KeyError:
            raise UnregisteredSourceError(
                f"source_id {source_id!r} is not registered — "
                f"a datapoint that cannot cite a registered public source is a bug"
            )

    def is_registered(self, source_id: str) -> bool:
        return source_id in self._sources

    def require(self, source_id: str) -> Source:
        """Assert a source_id is registered; raise if not. Call sites use this to
        enforce provenance before emitting a recommendation."""
        return self.get(source_id)

    def all(self) -> list[Source]:
        return list(self._sources.values())


# --- Canonical source definitions --------------------------------------------
# The stub source is always available; real providers register their own.
STUB_SOURCE = Source(
    id="STUB",
    authority="STUB",
    trust=TrustTier.STUB,
    description="Deterministic offline synthetic bars — development/tests only, "
                "NOT a basis for real decisions",
    public=True,
)

YAHOO_SOURCE = Source(
    id="YAHOO_FINANCE",
    authority="YAHOO_FINANCE",
    trust=TrustTier.CONVENIENCE,
    description="Public historical prices via yfinance — convenience data, not "
                "system-of-record",
    public=True,
)


def default_registry() -> SourceRegistry:
    """A registry pre-loaded with the always-available STUB source."""
    reg = SourceRegistry()
    reg.register(STUB_SOURCE)
    return reg
