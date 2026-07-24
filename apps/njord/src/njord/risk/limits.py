"""limits.py — hard risk limits enforced in code before any order is approved.

Every limit here is a real check with a test. These run in front of the
execution layer; in this recommend-only build nothing downstream actually places
an order, but the limit logic is the genuine article so paper trading (and any
future guarded live build) is protected from bar one.

Limits:
  - max position size (shares and notional)
  - max % of portfolio per name
  - max daily notional traded
  - max open orders
  - daily loss limit -> flatten + halt
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..config import RiskConfig


@dataclass(frozen=True)
class OrderIntent:
    symbol: str
    side: str          # "buy" or "sell"
    qty: int
    price: float

    @property
    def notional(self) -> float:
        return abs(self.qty) * self.price


@dataclass
class PortfolioState:
    equity: float = 100_000.0
    # symbol -> (shares, avg_price)
    positions: dict[str, tuple[int, float]] = field(default_factory=dict)
    open_orders: int = 0
    day_notional_used: float = 0.0     # notional already traded today
    realized_pnl_today: float = 0.0    # realized P&L today (negative = loss)
    halted: bool = False

    def position_shares(self, symbol: str) -> int:
        return self.positions.get(symbol.upper(), (0, 0.0))[0]

    def position_notional(self, symbol: str, price: float) -> float:
        return abs(self.position_shares(symbol)) * price


@dataclass(frozen=True)
class LimitBreach:
    code: str
    message: str


@dataclass
class LimitCheck:
    approved: bool
    breaches: list[LimitBreach] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "approved": self.approved,
            "breaches": [{"code": b.code, "message": b.message} for b in self.breaches],
        }


class RiskLimits:
    def __init__(self, config: RiskConfig | None = None) -> None:
        self.cfg = config or RiskConfig()

    def check(self, order: OrderIntent, state: PortfolioState) -> LimitCheck:
        breaches: list[LimitBreach] = []
        cfg = self.cfg
        sym = order.symbol.upper()

        if state.halted:
            breaches.append(LimitBreach("HALTED", "trading is halted"))

        # Kill/halt from daily loss: if today's realized loss meets the limit,
        # nothing new may open.
        if state.realized_pnl_today <= -abs(cfg.daily_loss_limit):
            breaches.append(
                LimitBreach(
                    "DAILY_LOSS_LIMIT",
                    f"daily loss limit ${cfg.daily_loss_limit:.2f} reached "
                    f"(realized {state.realized_pnl_today:.2f}) — flatten + halt",
                )
            )

        # Resulting position size after this order.
        cur_shares = state.position_shares(sym)
        delta = order.qty if order.side == "buy" else -order.qty
        new_shares = cur_shares + delta

        if abs(new_shares) > cfg.max_position_shares:
            breaches.append(
                LimitBreach(
                    "MAX_POSITION_SHARES",
                    f"{abs(new_shares)} shares exceeds max {cfg.max_position_shares}",
                )
            )

        new_notional = abs(new_shares) * order.price
        if new_notional > cfg.max_position_notional:
            breaches.append(
                LimitBreach(
                    "MAX_POSITION_NOTIONAL",
                    f"${new_notional:.2f} position exceeds max "
                    f"${cfg.max_position_notional:.2f}",
                )
            )

        # % of portfolio per name.
        if state.equity > 0:
            pct = new_notional / state.equity
            if pct > cfg.max_pct_portfolio_per_name:
                breaches.append(
                    LimitBreach(
                        "MAX_PCT_PER_NAME",
                        f"{pct * 100:.1f}% of portfolio in {sym} exceeds max "
                        f"{cfg.max_pct_portfolio_per_name * 100:.1f}%",
                    )
                )

        # Daily notional.
        if state.day_notional_used + order.notional > cfg.max_daily_notional:
            breaches.append(
                LimitBreach(
                    "MAX_DAILY_NOTIONAL",
                    f"daily notional ${state.day_notional_used + order.notional:.2f} "
                    f"exceeds max ${cfg.max_daily_notional:.2f}",
                )
            )

        # Open orders.
        if state.open_orders + 1 > cfg.max_open_orders:
            breaches.append(
                LimitBreach(
                    "MAX_OPEN_ORDERS",
                    f"{state.open_orders + 1} open orders exceeds max "
                    f"{cfg.max_open_orders}",
                )
            )

        return LimitCheck(approved=(len(breaches) == 0), breaches=breaches)

    def daily_loss_breached(self, state: PortfolioState) -> bool:
        return state.realized_pnl_today <= -abs(self.cfg.daily_loss_limit)

    def flatten_and_halt(self, state: PortfolioState) -> PortfolioState:
        """Enforce the daily-loss halt: drop all positions and set halted.

        Returns the mutated state (also mutates in place). This is what the
        execution loop calls the instant the daily loss limit is hit.
        """
        state.positions = {}
        state.open_orders = 0
        state.halted = True
        return state
