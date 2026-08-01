#!/usr/bin/env python3
"""Store entry point — `make run app=kitchen-pudding`.

The Makefile runs `python3 app.py` in the app directory, and this tool's real
surface is `kitchen_pudding/cli.py`. Rather than duplicate its argument
parser, this delegates, so `make run` and `python3 -m kitchen_pudding.cli`
cannot drift.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from kitchen_pudding.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
