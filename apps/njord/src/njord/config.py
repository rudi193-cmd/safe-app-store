"""config.py — Njord configuration: risk limits, gate thresholds, secrets seam.

Secrets are ONLY ever read from the environment (or an OS keyring, when wired) —
never committed, never written to the repo. This module deliberately contains no
credentials; it only knows the *names* of the env vars to look at.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


# --- Risk limits (hard caps enforced in code before any order is approved) ----
@dataclass(frozen=True)
class RiskConfig:
    max_position_shares: int = 1_000          # max shares in a single position
    max_position_notional: float = 10_000.0   # max $ in a single position
    max_pct_portfolio_per_name: float = 0.20  # <=20% of portfolio in one name
    max_daily_notional: float = 50_000.0      # max $ traded in one day
    max_open_orders: int = 20                 # max simultaneously open orders
    daily_loss_limit: float = 2_000.0         # $ realized loss that halts + flattens
    pdt_min_equity: float = 25_000.0          # PDT rule threshold for margin accts
    pdt_window_days: int = 5                  # business-day lookback window
    pdt_max_day_trades: int = 3               # 4th day-trade in window is blocked


# --- Live-gate thresholds (paper-first) ---------------------------------------
@dataclass(frozen=True)
class GateConfig:
    # Minimum paper track record before live is even *considerable*.
    min_paper_fills: int = 50
    min_paper_days: int = 20
    # Env var names (values are NEVER stored here).
    live_credential_env: str = "NJORD_LIVE_CREDENTIAL"
    live_confirm_env: str = "NJORD_I_UNDERSTAND_LIVE"
    # The exact confirmation phrase a human must set to acknowledge live risk.
    live_confirm_phrase: str = "I-UNDERSTAND-LIVE"


@dataclass(frozen=True)
class Config:
    risk: RiskConfig = RiskConfig()
    gate: GateConfig = GateConfig()
    # SEC/EDGAR and most public APIs ask for a descriptive User-Agent.
    user_agent: str = "njord-safe-app (local personal research)"


def load() -> Config:
    """Load config. Overridable via env, but never reads secret *values* into
    the returned object — those stay in the environment."""
    return Config()


def get_secret(env_name: str) -> str | None:
    """Single seam for secret retrieval. Env only in this build; an OS-keyring
    lookup can be added here later without touching call sites."""
    return os.environ.get(env_name)
