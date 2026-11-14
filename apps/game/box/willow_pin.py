"""willow_pin.py: where the box finds willow, held to the pin. Python 3.9+.

The box plays with willow's kernel and add-ons where they live, in willow;
apps/game/willow.pin.json pins them: willow's commit, and each file the box
runs at that commit by its SHA-256. `root()` finds a willow checkout and
gives its folder only if every pinned file is there with its pinned bytes.

Where it looks, in order: WILLOW_ROOT, if set; then a checkout beside
safe-app-store named Willow or willow, the way the store's CI checks out a
sibling repository. A checkout missing a file, or holding one that differs,
is refused by name: the box never runs on a willow it wasn't pinned to.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
PIN = HERE.parent / "willow.pin.json"
STORE = HERE.parents[2]  # safe-app-store, holding apps/game/box


class Unpinned(RuntimeError):
    """No willow checkout holds the pinned files; the message says what."""


def pin() -> dict:
    return json.loads(PIN.read_text(encoding="utf-8"))


def candidates() -> list[Path]:
    found = [Path(os.environ["WILLOW_ROOT"])] if os.environ.get("WILLOW_ROOT") else []
    return found + [STORE.parent / "Willow", STORE.parent / "willow"]


def drift(root: Path, pinned: dict) -> list[str]:
    """The pinned files a checkout is missing, or holds with other bytes."""
    out = []
    for rel, want in pinned["files"].items():
        f = root / rel
        if not f.is_file():
            out.append(f"{rel} is missing")
        elif hashlib.sha256(f.read_bytes()).hexdigest() != want:
            out.append(f"{rel} differs")
    return out


def root() -> Path:
    """The willow checkout the box runs on, or Unpinned saying why not."""
    pinned, tried = pin(), []
    for c in candidates():
        if not (c / "kernel.py").is_file():
            tried.append(f"{c}: no willow there")
            continue
        off = drift(c, pinned)
        if not off:
            return c
        tried.append(
            f"{c}: {len(off)} file(s) off the pin at {pinned['commit'][:12]}, first {off[0]}"
        )
    raise Unpinned(
        f"no willow checkout matches the pin (willow {pinned['commit'][:12]}); "
        "set WILLOW_ROOT, or check willow out beside safe-app-store. "
        + "; ".join(tried)
    )
