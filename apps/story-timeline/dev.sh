#!/usr/bin/env bash
# dev.sh — Story Timeline local launcher
#
# Usage:
#   ./dev.sh              # launch TUI
#   ./dev.sh --serve      # browser mirror (textual serve)
#   ./dev.sh --import ~/Downloads/goodreads_library_export.csv
#
# Overrides:
#   STORY_TIMELINE_VENV=~/.venv ./dev.sh
#   WILLOW_ROOT=~/github/willow-2.0 ./dev.sh
#   STORY_TIMELINE_DISABLE_MCP=1 ./dev.sh   # run without Willow MCP

set -euo pipefail
cd "$(dirname "$0")"

APP_DATA="${APP_DATA:-$HOME/.willow/apps/story-timeline}"
VENV_DIR="${STORY_TIMELINE_VENV:-$APP_DATA/.venv}"

find_python() {
  if [[ -n "${STORY_TIMELINE_VENV:-}" && -x "${STORY_TIMELINE_VENV}/bin/python3" ]]; then
    echo "${STORY_TIMELINE_VENV}/bin/python3"
    return
  fi
  if [[ -x "$VENV_DIR/bin/python3" ]]; then
    echo "$VENV_DIR/bin/python3"
    return
  fi
  local candidates=(
    "$HOME/github/willow-2.0/.venv-dev/bin/python3"
    "$HOME/willow-2.0/.venv-dev/bin/python3"
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

export WILLOW_ROOT="${WILLOW_ROOT:-$HOME/github/willow-2.0}"
export WILLOW_DEV_SAFE_ROOT="${WILLOW_DEV_SAFE_ROOT:-$(cd .. && pwd)}"
export STORY_TIMELINE_DISABLE_MCP="${STORY_TIMELINE_DISABLE_MCP:-0}"
export APP_DATA

MCP_STATUS="enabled"
if [[ "${STORY_TIMELINE_DISABLE_MCP}" == "1" ]]; then
  MCP_STATUS="disabled"
elif [[ ! -f "$WILLOW_ROOT/sap/unified_mcp.sh" ]]; then
  MCP_STATUS="offline (WILLOW_ROOT not found — Jeles + KB suggestions unavailable)"
fi

echo "Story Timeline DEV: $(pwd)" >&2
echo "  python:     $PY" >&2
echo "  willow:     $WILLOW_ROOT" >&2
echo "  mcp:        $MCP_STATUS" >&2
echo "  db:         $HOME/.willow/store/story-timeline/timeline.db" >&2
echo "  log:        $HOME/.willow/story-timeline-mcp.log" >&2
echo "  keys:       a add  e edit  d delete  l link  p promote  j research  s suggest  i import  q quit" >&2

if [[ "${1:-}" == "--serve" ]]; then
  exec "$PY" -m textual serve app.py
elif [[ "${1:-}" == "--import" ]]; then
  exec "$PY" import_csv.py "${@:2}"
else
  exec "$PY" app.py "$@"
fi
