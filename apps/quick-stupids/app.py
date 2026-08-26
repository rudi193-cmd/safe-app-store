"""`make run app=quick-stupids` lands here — delegates to qstupid.main().

Positional args on the make invocation aren't easily threaded through
the Makefile, so the default here is `list` (safe, read-only). Run
`python apps/quick-stupids/qstupid.py {seed,list,check <claim>}` for the
full CLI.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from qstupid import main


if __name__ == "__main__":
    argv = sys.argv[1:] or ["list"]
    raise SystemExit(main(argv))
