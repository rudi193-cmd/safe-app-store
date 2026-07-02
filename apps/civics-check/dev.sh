#!/usr/bin/env bash
# dev.sh — Civics Check local launcher (Textual fair TUI, local SQLite).
#
# Runs standalone: no Willow checkout, no Postgres, no network required.
# Progress lives in apps/civics-check/civics_check.db (or cwd).
#
# Usage:
#   ./dev.sh          # rebuild catalog + launch fair TUI (default)
#   ./dev.sh --cli    # stdlib CLI menu (no Textual)
#
# Override venv:  CIVICS_CHECK_VENV=~/github/willow-2.0/.venv-dev ./dev.sh

set -euo pipefail
cd "$(dirname "$0")"

APP_DATA="${APP_DATA:-$HOME/.willow/apps/civics-check}"
VENV_DIR="${CIVICS_CHECK_VENV:-$APP_DATA/.venv}"

find_python() {
  if [[ -n "${CIVICS_CHECK_VENV:-}" && -x "${CIVICS_CHECK_VENV}/bin/python3" ]]; then
    echo "${CIVICS_CHECK_VENV}/bin/python3"
    return
  fi
  if [[ -x "$VENV_DIR/bin/python3" ]]; then
    echo "$VENV_DIR/bin/python3"
    return
  fi
  local candidates=(
    "$HOME/github/willow-2.0/.venv-dev/bin/python3"
    "../../.venv-dev/bin/python3"
    "$HOME/.willow/venv/bin/python3"
  )
  local c
  for c in "${candidates[@]}"; do
    if [[ -x "$c" ]]; then
      echo "$c"
      return
    fi
  done
  command -v python3
}

ensure_venv() {
  local py="$1"
  if [[ -x "$VENV_DIR/bin/python3" ]]; then
    py="$VENV_DIR/bin/python3"
  elif "$py" -c "import textual" 2>/dev/null; then
    echo "$py"
    return
  else
    echo "Creating venv at $VENV_DIR" >&2
    python3 -m venv "$VENV_DIR"
    py="$VENV_DIR/bin/python3"
  fi
  "$py" -m pip install -q --upgrade pip
  "$py" -m pip install -q -r requirements.txt
  echo "$py"
}

PY="$(ensure_venv "$(find_python)")"

echo "Civics Check DEV: $(pwd)" >&2
echo "  python:  $PY" >&2
echo "  db:      $(pwd)/civics_check.db" >&2
echo "  keys:    arrows/j/k navigate · Enter open · Esc back · q quit" >&2

"$PY" scripts/build_catalog.py

if [[ "${1:-}" == "--cli" ]]; then
  exec "$PY" app.py --cli
fi
exec "$PY" tui.py
