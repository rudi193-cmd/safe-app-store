#!/usr/bin/env python3
"""Store entry point — `make run app=field-acoustics`.

The Makefile runs `python3 app.py` in the app directory, and this tool's real
surface is `simulate.py` with a full argument parser. Rather than duplicate that
parser, this delegates, so `make run` and `python3 simulate.py` cannot drift.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from simulate import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
