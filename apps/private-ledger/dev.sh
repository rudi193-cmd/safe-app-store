#!/usr/bin/env bash
# dev.sh — Private Ledger local launcher (Textual TUI, local SQLite).
#
# Runs standalone: no Willow checkout, no Postgres, no network required.
# Ledger data lives in ~/.willow/private-ledger.db.
#
# Usage:   ./dev.sh
# Override venv location:  PRIVATE_LEDGER_VENV=~/some/venv ./dev.sh

set -euo pipefail
cd "$(dirname "$0")"

APP_DATA="${APP_DATA:-$HOME/.willow/apps/private-ledger}"
VENV_DIR="${PRIVATE_LEDGER_VENV:-$APP_DATA/.venv}"

if [[ ! -x "$VENV_DIR/bin/python3" ]]; then
  echo "Creating venv at $VENV_DIR" >&2
  python3 -m venv "$VENV_DIR"
fi
PY="$VENV_DIR/bin/python3"

"$PY" -m pip install -q --upgrade pip
"$PY" -m pip install -q -r requirements.txt

echo "Private Ledger DEV: $(pwd)" >&2
echo "  python:  $PY" >&2
echo "  db:      $HOME/.willow/private-ledger.db" >&2

exec "$PY" app.py "$@"
