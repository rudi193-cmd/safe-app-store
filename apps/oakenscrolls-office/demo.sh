#!/usr/bin/env bash
# demo.sh — zero-config demo on synthetic data (`make demo` convention).
# The sandbox IS the demo: repo-local, disposable, never touches ~/.willow.
exec "$(dirname "$0")/sandbox.sh" "$@"
