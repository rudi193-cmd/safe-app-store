"""engine.py — a minimal, pure backtest loop over historical bars.

Deliberately tiny and transparent. A single long/flat SMA-crossover strategy,
run bar-by-bar. The point of this module is not strategy sophistication — it is
to demonstrate a look-ahead-SAFE evaluation harness.

LOOK-AHEAD BIAS GUARD
---------------------
The signal for bar `i` is computed ONLY from bars[:i] (strictly before i), and
the resulting position is applied to the return realized from i-1 -> i has
already happened; we take the NEXT bar's return. Concretely: decide at close of
bar i using data up to and including i, earn the return of bar i+1. We never let
information from bar i+1 influence the decision made at bar i. The engine asserts
this invariant by construction (indices below).

WALK-FORWARD
------------
Walk-forward (re-fit on a rolling in-sample window, evaluate out-of-sample, roll)
is a documented stub — `walk_forward()` splits the series and calls `backtest`
on each out-of-sample slice, but parameter *fitting* is left as a TODO because
this build ships a single fixed-parameter strategy.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..data.models import Bar
from ..signals import features


@dataclass
class BacktestResult:
    symbol: str
    n_bars: int
    total_return: float          # cumulative strategy return (fraction)
    buy_hold_return: float       # benchmark
    n_trades: int
    equity_curve: list[float] = field(default_factory=list)
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "n_bars": self.n_bars,
            "total_return": round(self.total_return, 6),
            "buy_hold_return": round(self.buy_hold_return, 6),
            "n_trades": self.n_trades,
            "equity_curve_tail": [round(x, 6) for x in self.equity_curve[-5:]],
            "note": self.note,
        }


def backtest(
    bars: list[Bar],
    fast: int = 10,
    slow: int = 30,
) -> BacktestResult:
    """Long-when-fast-SMA-above-slow, flat otherwise. Look-ahead-safe.

    Position for bar transition i -> i+1 is decided using closes[:i+1] only,
    and earns the return of bar i+1. No future data leaks into any decision.
    """
    closes = [b.close for b in bars]
    n = len(closes)
    equity = [1.0]
    position = 0  # 0 flat, 1 long
    n_trades = 0

    # We can start making decisions once we have `slow` closes.
    for i in range(slow, n - 1):
        window = closes[: i + 1]  # data known AT bar i (inclusive) — no peeking
        fast_ma = features.sma(window, fast)
        slow_ma = features.sma(window, slow)
        desired = 1 if (fast_ma is not None and slow_ma is not None and fast_ma > slow_ma) else 0
        if desired != position:
            n_trades += 1
            position = desired
        # Earn the NEXT bar's return with the position decided above.
        prev_close = closes[i]
        next_close = closes[i + 1]
        bar_ret = (next_close - prev_close) / prev_close if prev_close else 0.0
        equity.append(equity[-1] * (1.0 + position * bar_ret))

    total_return = equity[-1] - 1.0 if equity else 0.0
    buy_hold = (closes[-1] / closes[slow] - 1.0) if n > slow and closes[slow] else 0.0

    return BacktestResult(
        symbol=bars[0].symbol if bars else "",
        n_bars=n,
        total_return=total_return,
        buy_hold_return=buy_hold,
        n_trades=n_trades,
        equity_curve=equity,
        note=(
            "Look-ahead-safe: each decision uses closes[:i+1] and earns bar i+1's "
            "return. Backtested performance is NOT predictive."
        ),
    )


def walk_forward(bars: list[Bar], folds: int = 3, fast: int = 10, slow: int = 30) -> list[BacktestResult]:
    """DOCUMENTED STUB: split into `folds` out-of-sample slices and backtest each.

    TODO: real walk-forward re-fits strategy parameters on each in-sample window
    before evaluating out-of-sample. This build ships fixed parameters, so we only
    demonstrate the rolling out-of-sample *evaluation* here.
    """
    if folds < 1:
        raise ValueError("folds must be >= 1")
    n = len(bars)
    size = max(slow + fast + 2, n // folds)
    results: list[BacktestResult] = []
    for start in range(0, n, size):
        chunk = bars[start : start + size]
        if len(chunk) > slow + 1:
            results.append(backtest(chunk, fast=fast, slow=slow))
    return results
