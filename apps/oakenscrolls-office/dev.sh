#!/usr/bin/env bash
# dev.sh — Oakenscroll's Office local launcher (Textual TUI, local SQLite).
#
# Runs standalone: no Willow checkout, no Postgres, no network required.
# The ledger lives in ~/.willow/store/oakenscrolls-office/office.db.
#
# Usage:   ./dev.sh            the Textual TUI
#          ./dev.sh --serve    the web mirror (reliability diagram) instead
# Override venv location:  OAKENSCROLL_VENV=~/some/venv ./dev.sh

set -euo pipefail
cd "$(dirname "$0")"

APP_DATA="${APP_DATA:-$HOME/.willow/apps/oakenscrolls-office}"
VENV_DIR="${OAKENSCROLL_VENV:-$APP_DATA/.venv}"

if [[ ! -x "$VENV_DIR/bin/python3" ]]; then
  echo "Creating venv at $VENV_DIR" >&2
  python3 -m venv "$VENV_DIR"
fi
PY="$VENV_DIR/bin/python3"

"$PY" -m pip install -q --upgrade pip
"$PY" -m pip install -q -r requirements.txt

echo "Oakenscroll's Office DEV: $(pwd)" >&2
echo "  python:  $PY" >&2
echo "  ledger:  ${OAKENSCROLL_DB:-$HOME/.willow/store/oakenscrolls-office/office.db}" >&2

if [[ "${1:-}" == "--serve" ]]; then
  exec "$PY" web.py "${@:2}"
fi
exec "$PY" app.py "$@"
