"""Make `import homestead_health` work from a bare checkout.

The store's app-tests CI leg installs an app's `requirements.txt` (the engine
pin) and runs `python -m pytest tests/ -q` from the app directory without
installing the app itself. Inserting the app root keeps that leg and a cold
`pytest -q` honest without an out-of-band install step — the engine's I-28
posture, one rung earlier in the app's life. `pip install -e .` works too and
makes this line a no-op.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
