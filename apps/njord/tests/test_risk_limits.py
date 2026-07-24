"""Each hard limit triggers correctly; the daily-loss halt flattens + halts."""
from njord.config import RiskConfig
from njord.risk.limits import RiskLimits, OrderIntent, PortfolioState


def _limits():
    return RiskLimits(RiskConfig())


def test_approves_a_reasonable_order():
    lim = _limits()
    state = PortfolioState(equity=100_000.0)
    order = OrderIntent("AAPL", "buy", qty=10, price=100.0)  # $1k, 1%
    res = lim.check(order, state)
    assert res.approved, res.to_dict()


def test_max_position_shares():
    lim = _limits()
    state = PortfolioState(equity=100_000_000.0)
    order = OrderIntent("AAPL", "buy", qty=2_000, price=1.0)  # 2000 > 1000 shares
    res = lim.check(order, state)
    assert not res.approved
    assert any(b.code == "MAX_POSITION_SHARES" for b in res.breaches)


def test_max_position_notional():
    lim = _limits()
    state = PortfolioState(equity=100_000_000.0)
    order = OrderIntent("AAPL", "buy", qty=500, price=100.0)  # $50k > $10k
    res = lim.check(order, state)
    assert not res.approved
    assert any(b.code == "MAX_POSITION_NOTIONAL" for b in res.breaches)


def test_max_pct_per_name():
    lim = _limits()
    state = PortfolioState(equity=10_000.0)  # small book
    order = OrderIntent("AAPL", "buy", qty=50, price=100.0)  # $5k = 50% > 20%
    res = lim.check(order, state)
    assert not res.approved
    assert any(b.code == "MAX_PCT_PER_NAME" for b in res.breaches)


def test_max_daily_notional():
    lim = _limits()
    state = PortfolioState(equity=100_000_000.0, day_notional_used=49_000.0)
    order = OrderIntent("AAPL", "buy", qty=20, price=100.0)  # +$2k -> $51k > $50k
    res = lim.check(order, state)
    assert not res.approved
    assert any(b.code == "MAX_DAILY_NOTIONAL" for b in res.breaches)


def test_max_open_orders():
    lim = _limits()
    state = PortfolioState(equity=100_000_000.0, open_orders=20)
    order = OrderIntent("AAPL", "buy", qty=1, price=10.0)
    res = lim.check(order, state)
    assert not res.approved
    assert any(b.code == "MAX_OPEN_ORDERS" for b in res.breaches)


def test_daily_loss_limit_blocks_new_orders():
    lim = _limits()
    state = PortfolioState(equity=100_000.0, realized_pnl_today=-2_500.0)  # past -$2k
    order = OrderIntent("AAPL", "buy", qty=1, price=10.0)
    res = lim.check(order, state)
    assert not res.approved
    assert any(b.code == "DAILY_LOSS_LIMIT" for b in res.breaches)
    assert lim.daily_loss_breached(state)


def test_flatten_and_halt():
    lim = _limits()
    state = PortfolioState(
        equity=100_000.0,
        positions={"AAPL": (100, 150.0), "MSFT": (50, 300.0)},
        open_orders=3,
        realized_pnl_today=-2_500.0,
    )
    lim.flatten_and_halt(state)
    assert state.positions == {}
    assert state.open_orders == 0
    assert state.halted is True
    # A halted book refuses any further order.
    res = lim.check(OrderIntent("AAPL", "buy", 1, 10.0), state)
    assert not res.approved
    assert any(b.code == "HALTED" for b in res.breaches)
