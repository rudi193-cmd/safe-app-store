#!/usr/bin/env bash
# dev.sh — Law Gazelle local development launcher
# b17: E472A · ΔΣ=42
#
# Usage:
#   ./dev.sh              # sync Nest DBs + launch dashboard
#   ./dev.sh --sync-only  # sync only, no UI
#
# Override paths:
#   NEST_SOURCE=~/Desktop/Nest ./dev.sh
#   LAW_GAZELLE_VENV=~/.willow/venv ./dev.sh

set -euo pipefail
cd "$(dirname "$0")"

APP_ID="law-gazelle"
NEST_SOURCE="${NEST_SOURCE:-$HOME/Desktop/Nest}"
APP_DATA="${APP_DATA:-$HOME/.willow/apps/$APP_ID}"
VENV_DIR="${LAW_GAZELLE_VENV:-$APP_DATA/.venv}"

find_python() {
  if [[ -n "${LAW_GAZELLE_VENV:-}" && -x "${LAW_GAZELLE_VENV}/bin/python3" ]]; then
    echo "${LAW_GAZELLE_VENV}/bin/python3"
    return
  fi
  if [[ -x "$VENV_DIR/bin/python3" ]]; then
    echo "$VENV_DIR/bin/python3"
    return
  fi
  local candidates=(
    "$HOME/.willow/venv/bin/python3"
    "$HOME/willow-2.0/.venv-dev/bin/python3"
    "$HOME/github/willow-2.0/.venv-dev/bin/python3"
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
  elif ! "$py" -c "import textual" 2>/dev/null; then
    echo "Creating venv at $VENV_DIR" >&2
    python3 -m venv "$VENV_DIR"
    py="$VENV_DIR/bin/python3"
  else
    echo "$py"
    return
  fi
  "$py" -m pip install -q --upgrade pip
  "$py" -m pip install -q -r requirements.txt
  echo "$py"
}

PY="$(ensure_venv "$(find_python)")"

export NEST_SOURCE
export APP_DATA

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo "?")"
BRANCH="$(git -C "$REPO_ROOT" branch --show-current 2>/dev/null || echo "?")"

echo "Law Gazelle DEV: $(pwd)" >&2
echo "  python:  $PY" >&2
echo "  app:     $(realpath app.py)" >&2
echo "  nest:    $NEST_SOURCE" >&2
echo "  cases:   $APP_DATA/cases" >&2
echo "  branch:  $BRANCH" >&2
echo "  ui:      TODAY WORKFLOW (single table + action deck — NOT 8 tabs)" >&2
echo "  ollama:  OLLAMA_MODEL=\${OLLAMA_MODEL:-llama3.2:3b} (local AI brief/draft/rank)" >&2
echo "  keys:    Enter=action deck  m=matters  d=drafts  s=session  a=activity  u=today  Esc=back" >&2
"$PY" app.py --check-ui
echo "  (quit any old Law Gazelle window before starting)" >&2

exec "$PY" app.py --source "$NEST_SOURCE" "$@"
