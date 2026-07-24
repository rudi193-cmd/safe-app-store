"""4th day-trade in 5 business days under $25k is blocked; over $25k allowed."""
from datetime import date

from njord.risk.pdt import PDTGuard


def _guard_with_three_trades():
    g = PDTGuard()
    # Mon..Wed of the same week — all within a 5-business-day window.
    g.record_day_trade("AAPL", date(2026, 7, 20))  # Mon
    g.record_day_trade("MSFT", date(2026, 7, 21))  # Tue
    g.record_day_trade("NVDA", date(2026, 7, 22))  # Wed
    return g


def test_fourth_day_trade_under_25k_is_blocked():
    g = _guard_with_three_trades()
    as_of = date(2026, 7, 23)  # Thu, same window
    assert len(g.day_trades_in_window(as_of)) == 3
    blocked, reason = g.check_and_reason(account_equity=10_000.0, as_of=as_of, is_margin=True)
    assert blocked, reason


def test_over_25k_is_allowed():
    g = _guard_with_three_trades()
    as_of = date(2026, 7, 23)
    assert not g.would_block(account_equity=30_000.0, as_of=as_of, is_margin=True)


def test_cash_account_not_subject_to_pdt():
    g = _guard_with_three_trades()
    as_of = date(2026, 7, 23)
    assert not g.would_block(account_equity=10_000.0, as_of=as_of, is_margin=False)


def test_three_or_fewer_is_allowed_under_25k():
    g = PDTGuard()
    g.record_day_trade("AAPL", date(2026, 7, 20))
    g.record_day_trade("MSFT", date(2026, 7, 21))
    as_of = date(2026, 7, 22)
    assert len(g.day_trades_in_window(as_of)) == 2
    assert not g.would_block(account_equity=10_000.0, as_of=as_of, is_margin=True)


def test_trades_outside_window_do_not_count():
    g = PDTGuard()
    # Three trades, but two weeks earlier — outside the 5-business-day window.
    g.record_day_trade("AAPL", date(2026, 7, 1))
    g.record_day_trade("MSFT", date(2026, 7, 2))
    g.record_day_trade("NVDA", date(2026, 7, 3))
    as_of = date(2026, 7, 23)
    assert g.day_trades_in_window(as_of) == []
    assert not g.would_block(account_equity=10_000.0, as_of=as_of, is_margin=True)
