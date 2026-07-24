"""features.py — transparent, pure-function technical indicators (stdlib only).

Everything here is deliberately simple and explainable so a recommendation's
rationale can name the exact number that drove it. No pandas, no TA-Lib — just
lists of floats in, floats/lists out. All functions are pure (no I/O, no state).
"""
from __future__ import annotations

from typing import Sequence


def sma(values: Sequence[float], window: int) -> float | None:
    """Simple moving average of the last `window` values. None if too short."""
    if window <= 0:
        raise ValueError("window must be positive")
    if len(values) < window:
        return None
    return sum(values[-window:]) / window


def returns(values: Sequence[float]) -> list[float]:
    """Simple period-over-period returns."""
    out: list[float] = []
    for prev, cur in zip(values, values[1:]):
        if prev == 0:
            out.append(0.0)
        else:
            out.append((cur - prev) / prev)
    return out


def momentum(values: Sequence[float], window: int) -> float | None:
    """Total return over the last `window` periods (close_t / close_{t-window} - 1)."""
    if window <= 0:
        raise ValueError("window must be positive")
    if len(values) <= window:
        return None
    past = values[-window - 1]
    now = values[-1]
    if past == 0:
        return None
    return (now - past) / past


def rsi(values: Sequence[float], window: int = 14) -> float | None:
    """Simple RSI (Wilder-style average of gains/losses over `window`).

    Returns a value in [0, 100], or None if there is not enough data.
    """
    if window <= 0:
        raise ValueError("window must be positive")
    if len(values) <= window:
        return None
    gains = 0.0
    losses = 0.0
    # Use the last `window` period-over-period changes.
    recent = values[-window - 1:]
    for prev, cur in zip(recent, recent[1:]):
        change = cur - prev
        if change >= 0:
            gains += change
        else:
            losses += -change
    avg_gain = gains / window
    avg_loss = losses / window
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))
