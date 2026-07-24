"""pdt.py — US Pattern Day Trader guard.

Rule encoded: on a MARGIN account with equity < $25,000, executing 4 or more
day-trades within any rolling window of 5 business days flags you as a Pattern
Day Trader. This guard blocks the 4th day-trade in the window when equity is
under the threshold. Cash accounts and accounts >= $25k are not blocked here.

A "day trade" = buying and selling (or short-and-cover) the same security on the
same trading day. We track completed day-trades with their business-date.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from ..config import RiskConfig


@dataclass(frozen=True)
class DayTrade:
    symbol: str
    day: date


def _business_days_between(a: date, b: date) -> int:
    """Count business days (Mon-Fri) in the inclusive window [a, b]."""
    if a > b:
        a, b = b, a
    days = 0
    d = a
    while d <= b:
        if d.weekday() < 5:  # 0=Mon .. 4=Fri
            days += 1
        d += timedelta(days=1)
    return days


class PDTGuard:
    def __init__(self, config: RiskConfig | None = None) -> None:
        self.cfg = config or RiskConfig()
        self._trades: list[DayTrade] = []

    def record_day_trade(self, symbol: str, day: date) -> None:
        self._trades.append(DayTrade(symbol.upper(), day))

    def day_trades_in_window(self, as_of: date) -> list[DayTrade]:
        """Day-trades falling within the rolling 5-business-day window ending
        at `as_of`."""
        window = self.cfg.pdt_window_days
        return [
            t
            for t in self._trades
            if t.day <= as_of and _business_days_between(t.day, as_of) <= window
        ]

    def would_block(self, account_equity: float, as_of: date, is_margin: bool = True) -> bool:
        """Return True if placing ANOTHER day-trade now would trip the PDT rule.

        Blocks when: margin account AND equity < threshold AND the number of
        day-trades already in the window is >= pdt_max_day_trades (i.e. this
        next one would be the 4th).
        """
        if not is_margin:
            return False
        if account_equity >= self.cfg.pdt_min_equity:
            return False
        existing = len(self.day_trades_in_window(as_of))
        return existing >= self.cfg.pdt_max_day_trades

    def check_and_reason(
        self, account_equity: float, as_of: date, is_margin: bool = True
    ) -> tuple[bool, str]:
        blocked = self.would_block(account_equity, as_of, is_margin)
        if not blocked:
            return False, "PDT ok"
        n = len(self.day_trades_in_window(as_of))
        return True, (
            f"PDT block: {n} day-trades in the last {self.cfg.pdt_window_days} "
            f"business days on a margin account with ${account_equity:,.0f} "
            f"(< ${self.cfg.pdt_min_equity:,.0f}); a 4th would flag you."
        )
