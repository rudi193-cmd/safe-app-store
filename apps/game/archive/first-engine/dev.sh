#!/usr/bin/env bash
# dev.sh — SAFE Game local launcher (Streamlit UI).
#
# Runs standalone: the SAP gate and Willow lattice are optional and degrade
# gracefully when a Willow checkout is absent.
#
# Usage:   ./dev.sh                  # launch the Streamlit app
# Override venv location:  GAME_VENV=~/some/venv ./dev.sh

set -euo pipefail
cd "$(dirname "$0")"

APP_DATA="${APP_DATA:-$HOME/.willow/apps/game}"
VENV_DIR="${GAME_VENV:-$APP_DATA/.venv}"

if [[ ! -x "$VENV_DIR/bin/python3" ]]; then
  echo "Creating venv at $VENV_DIR" >&2
  python3 -m venv "$VENV_DIR"
fi
PY="$VENV_DIR/bin/python3"

"$PY" -m pip install -q --upgrade pip
"$PY" -m pip install -q -r requirements.txt

echo "SAFE Game DEV: $(pwd)" >&2
echo "  python:  $PY" >&2

exec "$PY" -m streamlit run streamlit_app.py "$@"
