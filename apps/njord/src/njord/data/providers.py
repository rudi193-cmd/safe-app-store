"""providers.py — data providers.

- StubProvider: deterministic OFFLINE synthetic bars. The default. No network,
  no extra deps. Same ticker+params -> byte-identical bars, so recommend/backtest
  and the whole test suite are reproducible offline.
- YFinanceProvider: the optional real-data adapter. It LAZILY imports yfinance
  and raises a clear ProviderUnavailable if the package is missing or the fetch
  fails (e.g. offline). Registering it opts the app into public-API egress.

Every provider registers its Source in the given SourceRegistry and stamps every
Bar/Quote it returns with a Provenance pointing at that source.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Protocol

from .models import Bar, Provenance, Quote
from .registry import Source, SourceRegistry, TrustTier, YAHOO_SOURCE


class ProviderUnavailable(RuntimeError):
    """Raised when a provider cannot serve data (missing dep, offline, etc.)."""


class Provider(Protocol):
    source_id: str

    def bars(self, symbol: str, lookback: int = 120) -> list[Bar]: ...
    def quote(self, symbol: str) -> Quote: ...


# ----------------------------------------------------------------------------- #
# StubProvider — deterministic, offline, default                                #
# ----------------------------------------------------------------------------- #
class StubProvider:
    """Deterministic synthetic bars derived from a hash of the symbol.

    Fully offline. The price path is a smooth pseudo-random walk with a mild,
    symbol-dependent drift and seasonality so different tickers rank differently
    and momentum/mean-reversion signals have something to bite on.
    """

    source_id = "STUB"

    def __init__(self, registry: SourceRegistry) -> None:
        self._registry = registry
        # STUB is pre-registered by default_registry(); register if a bare
        # registry was supplied.
        if not registry.is_registered(self.source_id):
            registry.register(
                Source(
                    id="STUB",
                    authority="STUB",
                    trust=TrustTier.STUB,
                    description="Deterministic offline synthetic bars",
                )
            )

    def _seed(self, symbol: str) -> int:
        h = hashlib.sha256(symbol.upper().encode("utf-8")).hexdigest()
        return int(h[:8], 16)

    def bars(self, symbol: str, lookback: int = 120) -> list[Bar]:
        symbol = symbol.upper()
        seed = self._seed(symbol)
        # Deterministic parameters from the seed.
        base = 20.0 + (seed % 480)                 # base price 20..500
        drift = ((seed >> 3) % 21 - 10) / 5000.0   # per-bar drift, -0.2%..+0.2%
        amp = 0.02 + ((seed >> 7) % 8) / 100.0     # oscillation amplitude
        period = 8 + (seed >> 5) % 25              # oscillation period

        fetched_at = datetime.now(timezone.utc).isoformat()
        prov = Provenance(
            source_id=self.source_id,
            fetched_at=fetched_at,
            reference=f"stub://{symbol}?lookback={lookback}",
        )

        # Anchor timestamps to a fixed epoch so bars are reproducible.
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        bars: list[Bar] = []
        price = float(base)
        # A deterministic LCG for per-bar noise (no global random state).
        state = seed | 1
        for i in range(lookback):
            state = (1103515245 * state + 12345) & 0x7FFFFFFF
            noise = (state / 0x7FFFFFFF - 0.5) * 0.01  # +/-0.5%
            import math

            seasonal = amp * math.sin(2 * math.pi * i / period)
            ret = drift + seasonal / period + noise
            close = max(0.5, price * (1.0 + ret))
            high = max(price, close) * (1.0 + abs(noise))
            low = min(price, close) * (1.0 - abs(noise))
            open_ = price
            volume = 1_000_000 + (state % 500_000)
            ts = (start + timedelta(days=i)).date().isoformat()
            bars.append(
                Bar(
                    symbol=symbol,
                    ts=ts,
                    open=round(open_, 4),
                    high=round(high, 4),
                    low=round(low, 4),
                    close=round(close, 4),
                    volume=float(volume),
                    provenance=prov,
                )
            )
            price = close
        return bars

    def quote(self, symbol: str) -> Quote:
        last_bar = self.bars(symbol, lookback=1)[-1]
        last = last_bar.close
        spread = max(0.01, last * 0.0005)
        return Quote(
            symbol=symbol.upper(),
            ts=datetime.now(timezone.utc).isoformat(),
            bid=round(last - spread, 4),
            ask=round(last + spread, 4),
            last=last,
            provenance=Provenance(
                source_id=self.source_id,
                reference=f"stub://{symbol.upper()}/quote",
            ),
        )


# ----------------------------------------------------------------------------- #
# YFinanceProvider — optional real data, lazily imported                        #
# ----------------------------------------------------------------------------- #
class YFinanceProvider:
    """Opt-in real-data adapter. Public Yahoo Finance historical prices.

    yfinance is imported LAZILY inside each method so that:
      - the core package has zero hard dependencies,
      - importing njord never triggers network-capable code,
      - the tests run with no optional deps installed.
    A missing package or a failed/offline fetch raises ProviderUnavailable with
    a clear, actionable message.
    """

    source_id = "YAHOO_FINANCE"

    def __init__(self, registry: SourceRegistry) -> None:
        self._registry = registry
        if not registry.is_registered(self.source_id):
            registry.register(YAHOO_SOURCE)

    def _import_yf(self):
        try:
            import yfinance  # type: ignore
        except Exception as exc:  # pragma: no cover - exercised only w/ real dep
            raise ProviderUnavailable(
                "yfinance is not installed. Install the optional extra to use "
                "real data:  pip install 'safe-app-njord[realdata]'  "
                "(the default StubProvider needs no network and no extra deps)."
            ) from exc
        return yfinance

    def bars(self, symbol: str, lookback: int = 120) -> list[Bar]:
        yf = self._import_yf()
        symbol = symbol.upper()
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period=f"{max(lookback, 5)}d", auto_adjust=False)
        except Exception as exc:  # pragma: no cover - network path
            raise ProviderUnavailable(
                f"yfinance fetch failed for {symbol!r} (offline or rate-limited?): {exc}"
            ) from exc
        if hist is None or len(hist) == 0:  # pragma: no cover - network path
            raise ProviderUnavailable(
                f"yfinance returned no data for {symbol!r}"
            )
        fetched_at = datetime.now(timezone.utc).isoformat()
        prov = Provenance(
            source_id=self.source_id,
            fetched_at=fetched_at,
            reference=f"https://finance.yahoo.com/quote/{symbol}/history",
        )
        bars: list[Bar] = []
        for idx, row in hist.tail(lookback).iterrows():  # pragma: no cover
            bars.append(
                Bar(
                    symbol=symbol,
                    ts=str(getattr(idx, "date", lambda: idx)()),
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=float(row["Volume"]),
                    provenance=prov,
                )
            )
        return bars

    def quote(self, symbol: str) -> Quote:  # pragma: no cover - network path
        last_bar = self.bars(symbol, lookback=1)[-1]
        last = last_bar.close
        spread = max(0.01, last * 0.0005)
        return Quote(
            symbol=symbol.upper(),
            ts=datetime.now(timezone.utc).isoformat(),
            bid=last - spread,
            ask=last + spread,
            last=last,
            provenance=Provenance(
                source_id=self.source_id,
                reference=f"https://finance.yahoo.com/quote/{symbol.upper()}",
            ),
        )


def make_provider(name: str, registry: SourceRegistry) -> Provider:
    """Factory used by the CLI. Default is the offline stub."""
    name = (name or "stub").lower()
    if name in ("stub", "offline", "default"):
        return StubProvider(registry)
    if name in ("yfinance", "yahoo", "realdata"):
        return YFinanceProvider(registry)
    raise ValueError(f"unknown provider: {name!r} (use 'stub' or 'yfinance')")
