#!/usr/bin/env bash
# dev.sh — semantic-translator local launcher
#
# Usage:
#   ./dev.sh              # Textual TUI (default)
#   ./dev.sh scrape       # pull lessons from GitHub → data/corpus.jsonl
#   ./dev.sh demo         # seed built-in bilingual demo corpus (offline)
#   ./dev.sh play         # ¿Cómo se dice? — bilingual match quiz game
#   ./dev.sh ingest       # ingest corpus into Jeles
#   ./dev.sh query "text" # semantic search
#   ./dev.sh serve        # FastAPI web server at http://127.0.0.1:8432
#   ./dev.sh stats        # corpus statistics
#
# Override venv:
#   SEMANTIC_TRANSLATOR_VENV=~/my-venv ./dev.sh

set -euo pipefail
cd "$(dirname "$0")"

APP_DATA="${APP_DATA:-$HOME/.willow/apps/semantic-translator}"
VENV_DIR="${SEMANTIC_TRANSLATOR_VENV:-$APP_DATA/.venv}"

find_python() {
  if [[ -n "${SEMANTIC_TRANSLATOR_VENV:-}" && -x "${SEMANTIC_TRANSLATOR_VENV}/bin/python3" ]]; then
    echo "${SEMANTIC_TRANSLATOR_VENV}/bin/python3"
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
    [[ -x "$c" ]] && echo "$c" && return
  done
  command -v python3
}

ensure_venv() {
  local py="$1"
  if [[ -x "$VENV_DIR/bin/python3" ]]; then
    py="$VENV_DIR/bin/python3"
  elif "$py" -c "import textual, fastapi" 2>/dev/null; then
    echo "$py"
    return
  else
    echo "Creating venv at $VENV_DIR" >&2
    python3 -m venv "$VENV_DIR"
    py="$VENV_DIR/bin/python3"
  fi
  "$py" -m pip install -q --upgrade pip
  "$py" -m pip install -q -e .
  echo "$py"
}

PY="$(ensure_venv "$(find_python)")"

export WILLOW_ROOT="${WILLOW_ROOT:-$HOME/github/willow-2.0}"
export WILLOW_DEV_SAFE_ROOT="${WILLOW_DEV_SAFE_ROOT:-$(cd ../.. && pwd)}"
export APP_DATA

echo "SemanticTranslator DEV: $(pwd)" >&2
echo "  python:  $PY" >&2
echo "  willow:  $WILLOW_ROOT" >&2
echo "  corpus:  data/corpus.jsonl" >&2
echo "  log:     $HOME/.willow/semantic-translator.log" >&2
echo "" >&2

CMD="${1:-tui}"
shift 2>/dev/null || true

exec "$PY" -m semantic_translator.cli "$CMD" "$@"
