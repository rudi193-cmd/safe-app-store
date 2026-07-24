#!/usr/bin/env bash
# dev.sh — Private Ledger local launcher (Textual TUI, local SQLite).
#
# Runs standalone: no Willow checkout, no Postgres, no network required.
# Ledger data lives under $WILLOW_STORE_ROOT/private-ledger/private-ledger.db
# (default ~/.willow/store/private-ledger/private-ledger.db).
#
# Usage:   ./dev.sh                        # launch the TUI
#          ./dev.sh --web                  # human-facing local HTML mirror (127.0.0.1)
#          ./dev.sh --serve                # machine-facing stdio JSON (read-only)
#          ./dev.sh --serve --allow-write  # ...with writes enabled
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
# Editable install of the packaged app (pulls textual/httpx from pyproject and
# exposes the `private_ledger` package + `private-ledger` console script).
"$PY" -m pip install -q -e .

DB_DIR="${WILLOW_STORE_ROOT:-$HOME/.willow/store}/private-ledger"
echo "Private Ledger DEV: $(pwd)" >&2
echo "  python:  $PY" >&2
echo "  db:      $DB_DIR/private-ledger.db" >&2

exec "$PY" -m private_ledger "$@"
