#!/usr/bin/env bash
# dev.sh — AskJeles local launcher (Textual TUI + Willow jeles_sources)
#
# Usage:
#   ./dev.sh              # Jeles TUI (default)
#   ./dev.sh --demo       # offline seeded demo deck
#   ./dev.sh --trivia     # memory-ring benchmark
#   ./dev.sh --serve      # FastAPI verify API
#
# Override:
#   ASK_JELES_VENV=~/github/willow-2.0/.venv-dev ./dev.sh
#   WILLOW_ROOT=~/github/willow-2.0 ./dev.sh

set -euo pipefail
cd "$(dirname "$0")"

APP_DATA="${APP_DATA:-$HOME/.willow/apps/ask-jeles}"
VENV_DIR="${ASK_JELES_VENV:-$APP_DATA/.venv}"

find_python() {
  if [[ -n "${ASK_JELES_VENV:-}" && -x "${ASK_JELES_VENV}/bin/python3" ]]; then
    echo "${ASK_JELES_VENV}/bin/python3"
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
export ASK_JELES_USE_MCP="${ASK_JELES_USE_MCP:-1}"
export APP_DATA

# Report inference keys (never print values)
INFERENCE_STATUS="$("$PY" - <<'PY' 2>/dev/null || echo "unknown"
import sys
sys.path.insert(0, __import__("os").environ.get("WILLOW_ROOT", ""))
try:
    from core.inference_router import _load_key
    parts = []
    for label, names in (
        ("groq", ("GROQ_API_KEY", "WILLOW_GROQ_API_KEY")),
        ("gemini", ("GEMINI_API_KEY", "WILLOW_GEMINI_API_KEY")),
    ):
        ok = bool(_load_key(*names))
        parts.append(f"{label}:{'ok' if ok else '—'}")
    print(", ".join(parts))
except Exception:
    print("unavailable")
PY
)"

echo "AskJeles DEV: $(pwd)" >&2
echo "  python:     $PY" >&2
echo "  willow:     $WILLOW_ROOT" >&2
echo "  inference:  $INFERENCE_STATUS  (auto: ollama → gemini → groq)" >&2
echo "  log:        $HOME/.willow/jeles.log" >&2
echo "  keys:       Enter/o open  a synthesize  Ctrl+T quiz  m MCP  Ctrl+L learning  Ctrl+S save  Ctrl+Q quit" >&2

exec "$PY" -m askjeles.crown "$@"
