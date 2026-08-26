"""Playground entry point — `make run app=fleet-glue` lands here.

Delegates to :func:`fleet_glue.__main__.main`. Adding ``src/`` to sys.path
first so the app runs without a pip install.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from fleet_glue.__main__ import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
