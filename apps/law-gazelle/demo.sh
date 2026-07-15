#!/usr/bin/env bash
# demo.sh — zero-config Law Gazelle demo on synthetic case data.
# b17: E472A · ΔΣ=42
#
# Seeds a fictional Nest under .demo/ and launches the TUI against it.
# Touches nothing outside .demo/ — your real Nest and app data are never read.
#
# Usage:
#   ./demo.sh             # seed + launch
#   ./demo.sh --fresh     # wipe .demo/ entirely (sidecar state too), then launch
#   make demo             # same, from the repo root

set -euo pipefail
cd "$(dirname "$0")"

DEMO_ROOT="${LAW_GAZELLE_DEMO_ROOT:-$(pwd)/.demo}"

if [[ "${1:-}" == "--fresh" ]]; then
  rm -rf "$DEMO_ROOT"
  shift
fi

export NEST_SOURCE="$DEMO_ROOT/nest"
export APP_DATA="$DEMO_ROOT/app"

python3 scripts/seed_demo.py "$NEST_SOURCE"

echo "Law Gazelle DEMO — all data below is synthetic" >&2
exec ./dev.sh "$@"
