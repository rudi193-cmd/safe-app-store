# njord

Local-only, stdio-driven equities **analysis + recommendation** engine.
Verified public sources only, with first-class provenance.

> **RECOMMEND-ONLY.** No live trading. No broker orders. No real-money path.
> The `live` subcommand always **refuses**, and the `LiveAdapter` always raises
> `LiveTradingDisabled`. There is no code path that places a real order.
>
> This is personal-use research software. Nothing it prints is financial advice.

Named for Njörðr — the Norse god of sea, wind, and wealth-at-anchor. Fitting for
a tool built to stay in harbor: it reads the weather, ranks the ideas, and never
leaves the dock.

## What it is

A pure-Python core library behind a thin stdio CLI, structured as the six layers
from `docs/local-stock-trader-plan.md`:

```
data → signals → backtest → risk/portfolio → execution → journal
```

- **data** — provenance-carrying `Bar`/`Quote`, a `SourceRegistry`, and providers.
  The default `StubProvider` is deterministic and **fully offline**. The optional
  `YFinanceProvider` lazily imports `yfinance` for real public data.
- **signals** — transparent stdlib indicators (SMA, momentum, simple RSI) and a
  ranker that emits ideas, each with a rationale and a **provenance block**.
- **backtest** — a minimal, look-ahead-safe backtest loop (walk-forward stub).
- **risk** — real, tested hard limits, a Pattern-Day-Trader guard, a paper-first
  **live gate** (`is_live_authorized()` is `False` by default), and a **kill
  switch** with a dead-man's-file.
- **execution** — a `PaperAdapter` that simulates fills locally (idempotent by
  client id) and a `LiveAdapter` that **always refuses**.
- **journal** — an append-only JSONL audit log; every decision is written with
  its provenance.

## Install / run from source

Core is **stdlib only** — no dependencies to run `recommend`/`backtest`/`fetch`
on the offline stub, and none to run the test suite.

```bash
./dev.sh recommend AAPL MSFT NVDA     # ranked ideas w/ sources (offline stub)
./dev.sh fetch AAPL                    # normalized, provenance-tagged JSON
./dev.sh backtest AAPL                 # minimal backtest on stub data
./dev.sh paper AAPL --qty 10           # simulated fill (no network)
./dev.sh live AAPL                     # REFUSES: prints gate status, exits non-zero
./dev.sh kill                          # engage the kill switch
./dev.ps1 recommend AAPL               # Windows (PowerShell)
```

State (journal, kill-switch file, cache) lives under
`$WILLOW_STORE_ROOT/njord/` (default `~/.willow/store/njord/`).

### Opt-in real data

```bash
pip install "safe-app-njord[realdata]"       # installs yfinance
./dev.sh recommend AAPL --provider yfinance  # public Yahoo Finance data
```

The core never imports `yfinance` unless you select that provider. Secrets (for
any future authenticated source) are read **only from the environment / OS
keyring** — never committed.

## Provenance is enforced

Every datapoint carries a `source_id` + `fetched_at`. Before an idea is emitted,
the ranker checks each contributing bar's source against the `SourceRegistry`;
an idea that cannot cite a **registered** source raises `UnregisteredSourceError`
rather than being emitted. A recommendation without provenance is a bug.

## Safety invariants (audited)

1. No code path places a real order — `LiveAdapter.place_order` always raises;
   `live` refuses with a non-zero exit.
2. Tests run fully offline (no network, no `yfinance`) via `StubProvider`.
3. Every recommendation carries a provenance block tracing to a registered source.
4. Kill switch + paper-first gate + hard risk limits are real, enforced, tested.
5. No secrets/keys committed; secrets only via env.

## Tests

```bash
python -m venv .venv && . .venv/bin/activate
pip install pytest
pytest -q            # fully offline, no optional deps
```

## License

MIT — see `LICENSE`.
