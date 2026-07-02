#!/usr/bin/env python3
"""Preview the hero star field + FREEDOM 250 mark at a few widths."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import tui_art  # noqa: E402

for width in (60, 90, 120):
    field = tui_art.hero_field(width)
    lines = field.plain.splitlines()
    print(f"── width {width} — {len(lines)} rows ──")
    for line in lines:
        print(line)
print("ok")
