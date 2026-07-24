# Local-Only Stdio Stock Trader — Architecture & Build Plan

*A pure-Python, local-only, stdio-driven equities analysis + recommendation + live-execution engine, built from existing open-source projects and fed only by verified, public data sources. Researched July 2026.*

---

## Read this first (the honest part)

This plan is for **building software**, not for telling you what to buy — I'm not a financial advisor, and nothing here is a recommendation to trade. A bot that places real orders can lose real money fast, including more than you put in if you ever touch margin or options. So the whole design below treats **live execution as the last and most guarded step**, gated behind paper trading, hard risk limits, and a kill switch. Build it because it's a genuinely fun and deep engineering project; run it live only once you've watched it behave for a long time on fake money.

---

## Design principles

Everything follows from four constraints you set:

**Local-only.** No SaaS backend, no cloud database, no hosted strategy service. All code, models, state, and secrets live on your machine. The only network calls are outbound to *public data APIs* and, at the very end, your broker. This also makes it auditable — you can see every byte that leaves.

**Stdio.** The engine is a library with a thin stdio front end: a CLI (`stdin`/`stdout`, JSON or line protocol) so it composes with pipes, cron, and your existing tooling. You said your MCP layer is already handled, so this plan stops at a clean stdio/library seam — your MCP server just imports the same core package and calls the same functions the CLI does. No duplicated logic.

**Verified & public sources only.** Every data point that influences a recommendation must trace back to a named, public, authoritative source — SEC EDGAR filings, exchange/broker market data, the Fed's FRED. No scraped forums, no paywalled "signals," no mystery CSVs. Provenance is a first-class feature (see the source-registry section).

**Paper-first, always.** Identical code path for paper and live; the only difference is a credentials flag. You cannot reach live mode without explicitly clearing a gate.

---

## The architecture (six layers + stdio shell)

```
        ┌─────────────────────────────────────────────┐
        │  stdio shell: CLI  (your MCP imports core)   │
        └─────────────────────────────────────────────┘
                              │
   1. DATA  ──►  2. SIGNALS  ──►  3. BACKTEST  ──►  4. RISK/PORTFOLIO
   (ingest &      (features &      (validate on      (position sizing,
   normalize,     ML/rules →       history, walk-    limits, PDT,
   provenance)    ranked ideas)    forward)          exposure caps)
                                                          │
                              5. EXECUTION  ◄─────────────┘
                              (paper → live, idempotent orders)
                                        │
                              6. JOURNAL / AUDIT
                              (every decision + its sources, immutable log)
```

Each layer is swappable and independently testable. Data doesn't know about brokers; execution doesn't know how a signal was made — it just gets a sized, risk-approved order with an attached rationale.

---

## The building blocks — existing projects to stand on

You asked to use existing repos, including big-corp ones. Here's the catalog, mapped to layers. All are open-source and permissively licensed (verify each license against your use before shipping).

### Layer 1 — Data (verified, public)

| Project | Who / License | Role |
|---|---|---|
| **OpenBB Platform** | OpenBB, open-source | The unifying data layer. One Python API over many public providers (yfinance, FMP, SEC, Intrinio, Tiingo…) with a consistent schema. Start here so you're not writing a dozen API clients. |
| **edgartools** | `dgunning`, MIT | Clean, typed access to **SEC EDGAR**: 10-K/10-Q, 8-K, XBRL financials, and **Form 3/4/5 insider** + **13F** filings. This is your gold-standard "verified public" fundamentals + insider source. |
| **alpaca-py** | Alpaca, official SDK | Market data API (bars, quotes, trades) for US equities — *and* your execution SDK later, so data and orders share one auth. |
| **yfinance** | open-source | Convenient historical prices for prototyping/backtests (via OpenBB or directly). Treat as convenience, not system-of-record. |
| **fredapi** | open-source | **FRED** macro series (rates, CPI, unemployment) straight from the St. Louis Fed — public and authoritative. |

### Layer 2 — Signals & strategy (rules + ML)

| Project | Who / License | Role |
|---|---|---|
| **Qlib** | **Microsoft**, MIT | The big-corp centerpiece. AI-oriented quant platform: alpha-factor engineering, supervised ML models, walk-forward, and an RL module. Its `RD-Agent` even automates strategy R&D. Use it to generate and rank candidate ideas from your data. |
| **FinRL / FinRL-X** | AI4Finance Foundation | Reinforcement-learning trading framework if you want an agent that learns allocation policies rather than hand-coded rules. Heavier; optional. |
| **pandas-ta / TA-Lib** | open-source | Classic technical indicators (RSI, MACD, ATR…) for rule-based signals and features. Simple, transparent, easy to explain in a rationale. |

### Layers 3 — Backtesting

| Project | Who / License | Role |
|---|---|---|
| **NautilusTrader** | Nautech Systems | Production-grade, event-driven engine (Rust core, Python API) that runs the **same strategy code in backtest and live** — the right long-term home if you're serious. |
| **vectorbt** | open-source | Blazing vectorized backtests for fast idea screening across thousands of parameter sets. Great for the research loop before you commit a strategy to Nautilus. |
| **backtrader** | open-source | Gentler learning curve, huge community, has an Alpaca bridge. Fine for v1 if Nautilus feels heavy. |

### Layers 5 — Live execution (real money)

| Project | Who / License | Role |
|---|---|---|
| **alpaca-py** | Alpaca, official | Recommended broker for a first live build: commission-free US equities, **identical paper and live API** (flip one flag), REST + websockets. Simplest safe on-ramp. |
| **NautilusTrader + Interactive Brokers adapter** | Nautech / IBKR | The serious path. Nautilus ships a first-class **IBKR** live adapter. *Note:* Nautilus's Alpaca support is still an open RFC (issue #3374), **not** built in — so live Alpaca goes through `alpaca-py` directly, live IBKR goes through Nautilus. Pick one lane per broker. |

**Opinionated first build:** OpenBB + edgartools + FRED for data → pandas-ta + Qlib for signals → vectorbt then NautilusTrader for backtest → **alpaca-py paper → alpaca-py live** for execution. It gets you end-to-end on one broker with one auth and the least surface area, and you can graduate the execution engine to Nautilus/IBKR later without touching layers 1–4.

---

## Making "verified & public" real (not just a slogan)

Build a **source registry** as an actual module. Every provider is registered with an ID, the authority behind it (e.g. `SEC_EDGAR`, `FRED`, `ALPACA_MARKETDATA`), and a trust tier. Every datapoint that flows through the system carries its `source_id` and a fetch timestamp. Then:

- Every recommendation the engine emits ships with a **provenance block** — the exact filings, series, and bars that drove it, with URLs/accession numbers. If a signal can't cite a registered public source, it's a bug, and the engine refuses to act on it.
- Cache raw responses to a local, append-only store so a recommendation is **reproducible** — you can re-derive it byte-for-byte later. This is also your defense if you ever wonder "why did it buy that?"
- A nightly `verify` command re-pulls a sample and checks nothing drifted or 404'd.

This is what separates a toy from something you'd trust with money: not the strategy, but the fact that every decision is traceable to a public primary source.

---

## Live-execution safety (the part that protects your account)

Real orders demand guardrails an analysis tool never needs. Bake these into Layer 4–5 from day one, not later:

Paper-first gate — live mode requires a separate credential *and* an explicit `--i-understand-live` style confirmation plus a minimum paper track record you define. Hard risk limits enforced in code before any order leaves: max position size, max % of portfolio per name, max daily notional, max open orders, and a daily loss limit that flattens and halts. A kill switch — one command (and a dead-man's-file the loop checks each tick) that cancels all open orders and stops trading immediately. Idempotent, client-ID'd orders so a crash-and-restart never double-submits. Reconciliation on every startup: pull actual broker positions and open orders, compare to local state, refuse to trade if they disagree. Know the rules that apply to you — notably the US **Pattern Day Trader** rule (4+ day trades in 5 business days on a margin account under $25k gets you flagged); encode it so the bot won't trip it unintentionally. And a dry-run mode that logs the exact orders it *would* place without sending them.

None of this is optional for a live bot. It's most of the engineering, honestly — the strategy is the easy, fun 20%.

---

## Suggested repo layout & stdio seam

```
localtrader/
  core/
    data/          # OpenBB, edgartools, fredapi wrappers + source registry
    signals/       # pandas-ta features, Qlib models, ranking
    backtest/      # vectorbt screens, Nautilus strategy defs
    risk/          # position sizing, limits, PDT guard
    execution/     # alpaca-py adapter, idempotency, reconciliation
    journal/       # append-only audit log + provenance
    config.py      # paths, limits, source registry, secrets via env/keyring
  cli.py           # stdio front end: `localtrader recommend|backtest|paper|live|kill`
  tests/
```

The CLI is deliberately thin — it parses stdin/args and calls `core`. Your existing **MCP server imports `core` directly** and exposes the same functions as tools, so the LLM and the CLI are guaranteed to behave identically. Secrets go in the OS keyring or env vars, never in the repo.

---

## Phased roadmap (each phase is usable on its own)

**Phase 0 — Skeleton & data spine (weekend).** Package scaffold, `config`, source registry, and the CLI shell. Wire OpenBB + edgartools + fredapi so `localtrader fetch AAPL` returns normalized, provenance-tagged data.

**Phase 1 — Recommend-only.** Add pandas-ta features and a simple, transparent ranking (later swap in Qlib models). `localtrader recommend` prints ranked ideas *with their sources*. Fully useful, zero financial risk.

**Phase 2 — Backtest.** vectorbt for fast screening; port your chosen strategy into a NautilusTrader strategy class. Prove it walk-forward before it ever sees a live tick. Watch for look-ahead bias and overfitting — the two ways backtests lie.

**Phase 3 — Paper trading.** alpaca-py against the paper endpoint. Full risk layer, journal, reconciliation, kill switch. Run it for weeks. This is where you *actually* learn whether it works.

**Phase 4 — Live (guarded, tiny).** Same code, live credentials, the paper-first gate cleared, and position/loss limits set painfully small. Scale only after live behavior matches paper. Keep the kill switch within reach.

**Phase 5 — Graduate (optional).** Move execution to NautilusTrader + IBKR for a true event-driven engine; add Qlib/FinRL model research; add options/multi-asset only if you genuinely want that complexity.

---

## Compliance & reality notes

You're trading your own account with your own tool, which is generally fine, but a few things worth knowing: this is **personal-use software** — the moment you'd manage anyone else's money or publish recommendations, you're into regulatory territory (advisor registration, etc.), so keep it personal. Respect each **data provider's terms** (Alpaca, OpenBB providers, SEC's fair-access request headers and rate limits — EDGAR asks you to send a descriptive User-Agent). Expect to owe **taxes** on realized gains and keep the journal for records. And internalize that **backtested performance is not predictive** — most strategies that look great on history don't survive contact with live markets, which is exactly why the plan front-loads paper trading.

---

## Sources

- [OpenBB Platform (GitHub)](https://github.com/OpenBB-finance/OpenBB) · [data providers](https://docs.openbb.co/odp/python/faqs/data_providers)
- [edgartools (GitHub)](https://github.com/dgunning/edgartools) · [docs](https://edgartools.readthedocs.io/)
- [Microsoft Qlib (GitHub)](https://github.com/microsoft/qlib)
- [AI4Finance FinRL (GitHub)](https://github.com/AI4Finance-Foundation/FinRL) · [FinRL-Trading / FinRL-X](https://github.com/AI4Finance-Foundation/FinRL-Trading)
- [NautilusTrader](https://nautilustrader.io/) · [Interactive Brokers adapter](https://nautilustrader.io/docs/nightly/integrations/ib/) · [Alpaca integration RFC #3374](https://github.com/nautechsystems/nautilus_trader/issues/3374)
- [alpaca-py (official SDK)](https://github.com/alpacahq/alpaca-py) · [trading docs](https://alpaca.markets/sdks/python/trading.html)
- [Best Python backtest engines 2026 (NautilusTrader vs Backtrader vs VectorBT)](https://bullalert.ai/blog/best-python-backtest-engines-2026/)
