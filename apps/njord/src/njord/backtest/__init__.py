"""Njord backtest — minimal, pure, look-ahead-safe historical loop."""
from .engine import backtest, BacktestResult

__all__ = ["backtest", "BacktestResult"]
