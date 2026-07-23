#!/usr/bin/env bash
# dev.sh — The Nightstand local launcher (Textual TUI, local SQLite).
#
# Runs standalone: no Willow checkout, no Postgres, no network required.
# Things live in ~/.willow/store/the-nightstand/nightstand.db.
#
# Usage:   ./dev.sh
# Override venv location:  NIGHTSTAND_VENV=~/some/venv ./dev.sh

set -euo pipefail
cd "$(dirname "$0")"

APP_DATA="${APP_DATA:-$HOME/.willow/apps/the-nightstand}"
VENV_DIR="${NIGHTSTAND_VENV:-$APP_DATA/.venv}"

if [[ ! -x "$VENV_DIR/bin/python3" ]]; then
  echo "Creating venv at $VENV_DIR" >&2
  python3 -m venv "$VENV_DIR"
fi
PY="$VENV_DIR/bin/python3"

"$PY" -m pip install -q --upgrade pip
"$PY" -m pip install -q -r requirements.txt

echo "The Nightstand DEV: $(pwd)" >&2
echo "  python:  $PY" >&2
echo "  db:      ${NIGHTSTAND_DB:-$HOME/.willow/store/the-nightstand/nightstand.db}" >&2

exec "$PY" app.py "$@"
