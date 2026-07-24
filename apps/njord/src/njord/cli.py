"""cli.py — Njord stdio front end.

Thin argparse shell over the core library. Every subcommand parses args, calls
core, and prints JSON to stdout. An MCP server would import the same core and
call the same functions — no duplicated logic.

Subcommands:
  fetch <TICKER>          normalized, provenance-tagged bars/quote (JSON)
  recommend [TICKERS...]  ranked ideas WITH their sources (JSON)
  backtest <TICKER>       runs the engine on stub data (JSON)
  paper <TICKER>          simulated fill via PaperAdapter (no network)
  live <TICKER>           REFUSES — prints gate status, exits non-zero, no order
  kill                    engages the kill switch

Default provider = StubProvider, so recommend/backtest/fetch run with NO network
and NO extra deps. `--provider yfinance` opts into real public data.

SAFETY: `live` never places an order. It is a hard refusal.
"""
from __future__ import annotations

import argparse
import json
import sys

from .config import load as load_config
from .data.providers import make_provider
from .data.registry import default_registry
from .signals.rank import rank_candidates
from .backtest.engine import backtest as run_backtest
from .risk.gate import LiveGate
from .risk.killswitch import KillSwitch
from .execution.adapter import PaperAdapter, LiveAdapter, LiveTradingDisabled
from .execution.idempotency import IdempotencyStore
from .journal.journal import Journal


def _print(obj) -> None:
    json.dump(obj, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


def _provider_and_registry(name: str):
    registry = default_registry()
    provider = make_provider(name, registry)
    return provider, registry


# --- subcommand handlers ------------------------------------------------------
def cmd_fetch(args) -> int:
    provider, registry = _provider_and_registry(args.provider)
    bars = provider.bars(args.ticker, lookback=args.lookback)
    quote = provider.quote(args.ticker)
    out = {
        "ticker": args.ticker.upper(),
        "provider": args.provider,
        "quote": quote.to_dict(),
        "bars": [b.to_dict() for b in bars[-args.show :]] if args.show else [b.to_dict() for b in bars],
        "bar_count": len(bars),
    }
    _print(out)
    return 0


def cmd_recommend(args) -> int:
    provider, registry = _provider_and_registry(args.provider)
    tickers = [t.upper() for t in (args.tickers or ["AAPL", "MSFT", "NVDA", "GOOG", "AMZN"])]
    bars_by_symbol = {t: provider.bars(t, lookback=args.lookback) for t in tickers}
    ideas = rank_candidates(bars_by_symbol, registry)

    journal = Journal()
    result = []
    for idea in ideas:
        d = idea.to_dict()
        # Provenance block must be non-empty — enforced upstream in rank.build_idea.
        assert d["provenance"] and d["provenance"].get("source_ids"), "idea missing provenance"
        result.append(d)
        journal.append("recommend", {"symbol": idea.symbol, "score": idea.score,
                                      "side": idea.side, "rationale": idea.rationale},
                       provenance=d["provenance"])

    _print({"provider": args.provider, "count": len(result), "ideas": result})
    return 0


def cmd_backtest(args) -> int:
    provider, registry = _provider_and_registry(args.provider)
    bars = provider.bars(args.ticker, lookback=args.lookback)
    res = run_backtest(bars, fast=args.fast, slow=args.slow)
    _print({"provider": args.provider, "result": res.to_dict()})
    return 0


def cmd_paper(args) -> int:
    provider, registry = _provider_and_registry(args.provider)
    ks = KillSwitch()
    if ks.is_killed():
        _print({"refused": True, "reason": "kill switch engaged", "status": ks.status()})
        return 3
    quote = provider.quote(args.ticker)
    adapter = PaperAdapter(IdempotencyStore())
    fill = adapter.place_order(args.ticker, args.side, args.qty, quote.last)
    journal = Journal()
    journal.append("paper_fill", fill.to_dict(), provenance=quote.provenance.to_dict())
    _print({"mode": "paper", "fill": fill.to_dict()})
    return 0


def cmd_live(args) -> int:
    """REFUSE. Print gate status, journal the refusal, exit non-zero. No order."""
    gate = LiveGate()
    status = gate.status()
    adapter = LiveAdapter(gate)
    refused_reason = None
    try:
        adapter.place_order(args.ticker, args.side, args.qty, 0.0)
    except LiveTradingDisabled as exc:
        refused_reason = str(exc)

    journal = Journal()
    journal.append("live_refused",
                   {"ticker": args.ticker.upper(), "reason": refused_reason},
                   provenance={"gate": status.to_dict()})

    _print({
        "refused": True,
        "order_placed": False,
        "reason": refused_reason or "live trading disabled",
        "gate": status.to_dict(),
        "note": "Njord is recommend-only. No live trading. No broker orders.",
    })
    return 2  # non-zero


def cmd_kill(args) -> int:
    ks = KillSwitch()
    ks.engage(reason=args.reason)
    journal = Journal()
    journal.append("kill", ks.status())
    _print({"killed": True, "status": ks.status()})
    return 0


# --- parser -------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="njord",
        description="Local-only equities analysis + recommendation engine "
                    "(RECOMMEND-ONLY — no live trading).",
    )
    p.add_argument("--provider", default="stub",
                   help="data provider: 'stub' (default, offline) or 'yfinance' (opt-in real data)")
    p.add_argument("--lookback", type=int, default=120, help="bars of history")
    sub = p.add_subparsers(dest="cmd", required=True)

    fp = sub.add_parser("fetch", help="normalized, provenance-tagged data")
    fp.add_argument("ticker")
    fp.add_argument("--show", type=int, default=3, help="how many recent bars to print (0=all)")
    fp.set_defaults(func=cmd_fetch)

    rp = sub.add_parser("recommend", help="ranked ideas with their sources")
    rp.add_argument("tickers", nargs="*")
    rp.set_defaults(func=cmd_recommend)

    bp = sub.add_parser("backtest", help="run the backtest engine on stub data")
    bp.add_argument("ticker")
    bp.add_argument("--fast", type=int, default=10)
    bp.add_argument("--slow", type=int, default=30)
    bp.set_defaults(func=cmd_backtest)

    pp = sub.add_parser("paper", help="simulated fill via PaperAdapter (no network)")
    pp.add_argument("ticker")
    pp.add_argument("--side", default="buy", choices=["buy", "sell"])
    pp.add_argument("--qty", type=int, default=1)
    pp.set_defaults(func=cmd_paper)

    lp = sub.add_parser("live", help="REFUSES — prints gate status, exits non-zero")
    lp.add_argument("ticker")
    lp.add_argument("--side", default="buy", choices=["buy", "sell"])
    lp.add_argument("--qty", type=int, default=1)
    lp.set_defaults(func=cmd_live)

    kp = sub.add_parser("kill", help="engage the kill switch")
    kp.add_argument("--reason", default="manual")
    kp.set_defaults(func=cmd_kill)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
