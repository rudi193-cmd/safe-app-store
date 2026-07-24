"""Njord — local-only, stdio-driven equities analysis + recommendation engine.

RECOMMEND-ONLY BUILD. There is no code path that places a real order:
the LiveAdapter always raises LiveTradingDisabled and the `live` CLI refuses.
Every recommendation traces to a registered public source (provenance is a
first-class feature). Core is stdlib only; real market data is opt-in.
"""

__version__ = "0.1.0"
