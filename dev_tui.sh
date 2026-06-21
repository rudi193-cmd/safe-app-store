#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$SCRIPT_DIR/.venv-dev"

if [ ! -d "$VENV" ]; then
    echo "Creating venv..."
    python3 -m venv "$VENV"
fi

source "$VENV/bin/activate"

# Ensure deps
python3 -c "import textual, mcp" 2>/dev/null || pip install --quiet textual mcp

mkdir -p "$SCRIPT_DIR/data"

WILLOW_ALLOW_DEV_GATE=1 \
WILLOW_DEV_SAFE_ROOT="$HOME/github" \
    python3 "$SCRIPT_DIR/tui.py" "$@"
