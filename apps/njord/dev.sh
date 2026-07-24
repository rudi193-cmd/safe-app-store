#!/usr/bin/env bash
# dev.sh — Njord local launcher (stdio equities analysis + recommendation engine).
#
# RECOMMEND-ONLY. No live trading, no broker orders, no real-money path.
# The `live` subcommand always refuses; the LiveAdapter always raises.
#
# Runs standalone: no Willow checkout, no Postgres. Core is stdlib only and the
# default provider (StubProvider) is fully OFFLINE — no network, no extra deps.
# Journal + kill-switch state live under
#   $WILLOW_STORE_ROOT/njord/  (default ~/.willow/store/njord/).
#
# Usage:
#   ./dev.sh recommend AAPL MSFT NVDA        # ranked ideas w/ provenance (stub)
#   ./dev.sh fetch AAPL                       # normalized, provenance-tagged JSON
#   ./dev.sh backtest AAPL                    # minimal backtest on stub data
#   ./dev.sh paper AAPL --qty 10              # simulated fills, no network
#   ./dev.sh live AAPL                        # REFUSES (non-zero, no order)
#   ./dev.sh kill                             # engage the kill switch
#   ./dev.sh recommend AAPL --provider yfinance   # opt-in real data (needs extra)
#
# Override venv location:  NJORD_VENV=~/some/venv ./dev.sh ...

set -euo pipefail
cd "$(dirname "$0")"

APP_DATA="${APP_DATA:-$HOME/.willow/apps/njord}"
VENV_DIR="${NJORD_VENV:-$APP_DATA/.venv}"

if [[ ! -x "$VENV_DIR/bin/python3" ]]; then
  echo "Creating venv at $VENV_DIR" >&2
  python3 -m venv "$VENV_DIR"
fi
PY="$VENV_DIR/bin/python3"

"$PY" -m pip install -q --upgrade pip
# Editable install exposes the `njord` package + `njord` console script.
# Core has no dependencies; real data is the opt-in `[realdata]` extra.
"$PY" -m pip install -q -e .

STORE_DIR="${WILLOW_STORE_ROOT:-$HOME/.willow/store}/njord"
echo "Njord DEV: $(pwd)" >&2
echo "  python:  $PY" >&2
echo "  store:   $STORE_DIR" >&2
echo "  mode:    RECOMMEND-ONLY (live trading disabled)" >&2

exec "$PY" -m njord "$@"
