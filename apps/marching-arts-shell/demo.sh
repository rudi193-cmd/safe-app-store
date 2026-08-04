#!/usr/bin/env sh
# Zero-config wiring demo. `make demo app=marching-arts-shell` from the repo
# root, or ./demo.sh from here.
#
# Needs Node 22+ and a Chromium. It looks for one in the usual places and in
# PLAYWRIGHT_BROWSERS_PATH; set CHROME=/path/to/chrome if it cannot find yours.
# It does not skip when there is no browser — a demo that quietly does half of
# itself is worse than one that says it cannot run.
set -eu
cd "$(dirname "$0")"

if [ ! -d node_modules ]; then
  echo "installing dependencies…"
  npm ci --silent || npm install --silent
fi

if [ -z "${CHROME:-}" ] && [ -n "${PLAYWRIGHT_BROWSERS_PATH:-}" ]; then
  found="$(find "$PLAYWRIGHT_BROWSERS_PATH" -type f -name chrome 2>/dev/null | head -n 1 || true)"
  [ -n "$found" ] && CHROME="$found" && export CHROME
fi

exec node demo.mjs
